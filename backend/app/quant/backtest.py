"""Monthly, long-only, equal-weight top-N backtest of a factor composite, with trading costs.

At each month-end: score stocks with the composite (cross-sectional rank z-scores of the chosen
factors, weighted), hold the top N equally weighted until the next month-end, then rebalance.
Costs are charged on turnover. Benchmarks: the Nifty 50 price index and an equal-weight
portfolio of the whole universe (rebalanced monthly; a passive reference, not charged costs).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.quant.research import MIN_STOCKS


def rank_z(row: pd.Series) -> pd.Series:
    r = row.rank()
    return (r - r.mean()) / r.std(ddof=0) if r.std(ddof=0) > 0 else r * 0


def composite(factors: dict[str, pd.DataFrame], weights: dict[str, float], date: pd.Timestamp) -> pd.Series:
    """Weighted sum of rank z-scores; a stock needs every chosen factor to be scored."""
    total = sum(abs(w) for w in weights.values()) or 1.0
    parts = [rank_z(factors[k].loc[date].dropna()) * (w / total) for k, w in weights.items()]
    df = pd.concat(parts, axis=1)
    return df.dropna().sum(axis=1)


@dataclass(frozen=True)
class Metrics:
    months: int
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    max_drawdown: float | None
    total_return: float | None


def metrics(monthly: pd.Series, rf_annual: float) -> Metrics:
    r = monthly.dropna()
    n = len(r)
    if n < 3:
        return Metrics(n, None, None, None, None, None)
    growth = (1 + r).prod()
    cagr = growth ** (12 / n) - 1
    vol = r.std() * np.sqrt(12)
    excess = r.mean() * 12 - rf_annual
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    pct = lambda x: round(float(x) * 100, 2)  # noqa: E731
    return Metrics(n, pct(cagr), pct(vol), round(float(excess / vol), 2) if vol > 0 else None, pct(dd), pct(growth - 1))


@dataclass(frozen=True)
class Relative:
    excess_cagr: float | None  # strategy CAGR minus Nifty CAGR, % points
    beat_months_pct: float | None
    information_ratio: float | None


def relative(strategy: pd.Series, bench: pd.Series) -> Relative:
    pair = pd.concat([strategy, bench], axis=1, keys=["s", "b"]).dropna()
    if len(pair) < 3:
        return Relative(None, None, None)
    diff = pair["s"] - pair["b"]
    cagr = lambda r: (1 + r).prod() ** (12 / len(r)) - 1  # noqa: E731
    te = diff.std() * np.sqrt(12)
    return Relative(
        round(float(cagr(pair["s"]) - cagr(pair["b"])) * 100, 2),
        round(float((diff > 0).mean() * 100), 1),
        round(float(diff.mean() * 12 / te), 2) if te > 0 else None,
    )


@dataclass(frozen=True)
class BacktestResult:
    strategy: pd.Series  # net monthly returns, indexed by period start date
    gross: pd.Series
    nifty: pd.Series | None
    equal_weight: pd.Series
    turnover: pd.Series  # one-way turnover per rebalance (0-1)
    holdings: dict[pd.Timestamp, list[str]]


def run_backtest(
    factors: dict[str, pd.DataFrame],
    weights: dict[str, float],
    fwd: pd.DataFrame,
    bench_fwd: pd.Series | None,
    top_n: int,
    cost_per_side: float,
) -> BacktestResult:
    """`fwd` holds next-month returns per rebalance date; the last date (no forward return) is skipped."""
    gross, net, ew, turnover, holdings = {}, {}, {}, {}, {}
    prev: set[str] = set()
    for d in fwd.index[:-1]:
        score = composite(factors, weights, d)
        score = score[fwd.loc[d].reindex(score.index).notna()]  # needs a price next month
        if len(score) < max(MIN_STOCKS, top_n):
            continue
        picks = list(score.sort_values(ascending=False).index[:top_n])
        held = set(picks)
        one_way = 1.0 if not prev else len(held - prev) / top_n
        g = float(fwd.loc[d, picks].mean())
        cost = cost_per_side * (1.0 if not prev else 2 * one_way)
        gross[d], net[d], turnover[d], holdings[d] = g, g - cost, one_way, picks
        ew[d] = float(fwd.loc[d].dropna().mean())
        prev = held
    idx = pd.DatetimeIndex(list(net))
    nifty = bench_fwd.reindex(idx) if bench_fwd is not None else None
    return BacktestResult(
        strategy=pd.Series(net, index=idx, dtype=float),
        gross=pd.Series(gross, index=idx, dtype=float),
        nifty=nifty,
        equal_weight=pd.Series(ew, index=idx, dtype=float),
        turnover=pd.Series(turnover, index=idx, dtype=float),
        holdings=holdings,
    )
