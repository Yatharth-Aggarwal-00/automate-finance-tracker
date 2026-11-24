"""Glue between the database and the pure research code, with an in-process cache keyed on
the data, so repeated requests don't recompute factor panels."""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from app.quant import backtest as bt
from app.quant.data import Panel, load_panel
from app.quant.factors import available, compute_all
from app.quant.research import FactorReport, forward_returns, rebalance_dates, research_factor

TEST_YEARS = 3
RF_ANNUAL = 0.06  # risk-free rate for Sharpe ratios (approx. Indian T-bill yield; configurable per call)

CAVEATS = [
    "Compare strategies with the equal-weight universe first: it shares the universe's biases, "
    "so beating it is the fair test. Beating only the Nifty 50 can come from the biases below.",
    "Survivorship bias: the universe is today's Nifty 100, so stocks that dropped out of the index "
    "(often after falling) are missing from the past. This flatters historical results.",
    "Prices are not adjusted for dividends (stocks and the Nifty 50 price index alike), so returns "
    "understate total returns by roughly the dividend yield.",
    "Fills are assumed at month-end closing prices; costs are a flat percentage per side.",
    "Past factor performance does not guarantee future returns. This is research, not a recommendation.",
]


@dataclass
class Context:
    panel: Panel
    factors: dict[str, pd.DataFrame]
    dates: pd.DatetimeIndex
    fwd: pd.DataFrame
    bench_fwd: pd.Series | None
    test_start: pd.Timestamp
    reports: list[FactorReport] | None = None


_cache: dict[tuple, Context] = {}


def context(db: Session) -> Context:
    panel = load_panel(db)
    if panel.close.empty:
        return Context(panel, {}, pd.DatetimeIndex([]), pd.DataFrame(), None, pd.Timestamp.today())
    if panel.key in _cache:
        return _cache[panel.key]
    dates = rebalance_dates(panel.close.index)
    fwd = forward_returns(panel.close, dates)
    bench_fwd = None
    if panel.benchmark is not None:
        b = panel.benchmark.reindex(dates)
        bench_fwd = b.shift(-1) / b - 1
    last = dates[-1] if len(dates) else pd.Timestamp.today()
    test_start = last - pd.DateOffset(years=TEST_YEARS)
    ctx = Context(panel, compute_all(panel.close, panel.benchmark), dates, fwd, bench_fwd, test_start)
    _cache.clear()
    _cache[panel.key] = ctx
    return ctx


def factor_reports(ctx: Context) -> list[FactorReport]:
    if ctx.reports is None:
        ctx.reports = [research_factor(k, f, ctx.fwd, ctx.test_start) for k, f in ctx.factors.items()]
    return ctx.reports


@dataclass(frozen=True)
class PeriodMetrics:
    strategy: bt.Metrics
    nifty: bt.Metrics | None
    equal_weight: bt.Metrics
    vs_nifty: bt.Relative | None
    vs_equal_weight: bt.Relative
    avg_turnover: float | None


def _period(res: bt.BacktestResult, mask, rf: float) -> PeriodMetrics:
    s = res.strategy[mask]
    t = res.turnover[mask]
    return PeriodMetrics(
        strategy=bt.metrics(s, rf),
        nifty=bt.metrics(res.nifty[mask], rf) if res.nifty is not None else None,
        equal_weight=bt.metrics(res.equal_weight[mask], rf),
        vs_nifty=bt.relative(s, res.nifty[mask]) if res.nifty is not None else None,
        vs_equal_weight=bt.relative(s, res.equal_weight[mask]),
        avg_turnover=round(float(t.iloc[1:].mean()) * 100, 1) if len(t) > 1 else None,
    )


@dataclass(frozen=True)
class BacktestReport:
    weights: dict[str, float]
    top_n: int
    cost_per_side_pct: float
    test_start: pd.Timestamp
    full: PeriodMetrics
    train: PeriodMetrics
    test: PeriodMetrics
    curve: list[dict]
    latest_holdings: list[str]
    latest_date: pd.Timestamp | None


def run(ctx: Context, weights: dict[str, float], top_n: int, cost_bps: float, rf: float = RF_ANNUAL) -> BacktestReport:
    unknown = set(weights) - set(ctx.factors)
    if unknown:
        raise ValueError(f"Unknown or unavailable factors: {', '.join(sorted(unknown))}")
    res = bt.run_backtest(ctx.factors, weights, ctx.fwd, ctx.bench_fwd, top_n, cost_bps / 10_000)
    idx = res.strategy.index
    train_mask, test_mask = idx < ctx.test_start, idx >= ctx.test_start

    # Equity curves start at 100; each point is the value at the END of the holding month.
    curve, s, n, e = [], 100.0, 100.0, 100.0
    next_dates = {d: ctx.dates[i + 1] for i, d in enumerate(ctx.dates[:-1])}
    if len(idx):
        curve.append({"date": idx[0].date().isoformat(), "strategy": 100.0, "nifty": 100.0 if res.nifty is not None else None, "equal_weight": 100.0})
    for d in idx:
        s *= 1 + res.strategy[d]
        e *= 1 + res.equal_weight[d]
        if res.nifty is not None and pd.notna(res.nifty[d]):
            n *= 1 + res.nifty[d]
        curve.append({
            "date": next_dates[d].date().isoformat(),
            "strategy": round(s, 2),
            "nifty": round(n, 2) if res.nifty is not None else None,
            "equal_weight": round(e, 2),
        })
    last = idx[-1] if len(idx) else None
    return BacktestReport(
        weights=weights,
        top_n=top_n,
        cost_per_side_pct=cost_bps / 100,
        test_start=ctx.test_start,
        full=_period(res, slice(None), rf),
        train=_period(res, train_mask, rf),
        test=_period(res, test_mask, rf),
        curve=curve,
        latest_holdings=res.holdings[last] if last is not None else [],
        latest_date=last,
    )


@dataclass(frozen=True)
class ScreenRow:
    symbol: str
    sector: str
    score: float
    rank: int
    percentiles: dict[str, float | None]  # 0-100 per factor; higher = stronger on that factor


def screen(ctx: Context, weights: dict[str, float]) -> tuple[pd.Timestamp, list[ScreenRow]]:
    """Today's ranking by the composite. Research output, not a recommendation."""
    unknown = set(weights) - set(ctx.factors)
    if unknown:
        raise ValueError(f"Unknown or unavailable factors: {', '.join(sorted(unknown))}")
    d = ctx.panel.close.index[-1]
    score = bt.composite(ctx.factors, weights, d).sort_values(ascending=False)
    pct = {k: ctx.factors[k].loc[d].rank(pct=True) * 100 for k in ctx.factors}
    rows = [
        ScreenRow(
            symbol=sym,
            sector=ctx.panel.sectors.get(sym, ""),
            score=round(float(v), 3),
            rank=i + 1,
            percentiles={k: (round(float(p[sym]), 0) if pd.notna(p.get(sym)) else None) for k, p in pct.items()},
        )
        for i, (sym, v) in enumerate(score.items())
    ]
    return d, rows


def factor_catalog(ctx: Context):
    return available(ctx.panel.benchmark)
