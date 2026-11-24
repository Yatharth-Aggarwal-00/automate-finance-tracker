"""Cross-sectional factor research on monthly rebalance dates.

For each month-end t: rank stocks by the factor value at t and compare with each stock's return
from t to the next month-end. The Spearman rank correlation of the two is the information
coefficient (IC). A factor with a consistently positive IC ranked next month's winners above
next month's losers.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_STOCKS = 10


def rebalance_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each calendar month present in the data."""
    s = index.to_series()
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).max().values)


def forward_returns(close: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Return from each rebalance date to the next one (NaN for the last date)."""
    px = close.reindex(dates)
    return px.shift(-1) / px - 1


def information_coefficients(factor: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    ics = {}
    for d in fwd.index:
        pair = pd.concat([factor.loc[d], fwd.loc[d]], axis=1, keys=["f", "r"]).dropna()
        if len(pair) >= MIN_STOCKS:
            ics[d] = pair["f"].rank().corr(pair["r"].rank())
    return pd.Series(ics, dtype=float)


def quantile_returns(factor: pd.DataFrame, fwd: pd.DataFrame, buckets: int) -> pd.DataFrame:
    """Mean forward return of each factor bucket (1 = lowest factor values), per date."""
    out = {}
    for d in fwd.index:
        pair = pd.concat([factor.loc[d], fwd.loc[d]], axis=1, keys=["f", "r"]).dropna()
        if len(pair) >= max(MIN_STOCKS, buckets * 2):
            q = pd.qcut(pair["f"].rank(method="first"), buckets, labels=False) + 1
            out[d] = pair["r"].groupby(q).mean()
    return pd.DataFrame(out).T


@dataclass(frozen=True)
class FactorStats:
    months: int
    ic_mean: float | None
    ic_t: float | None  # t-statistic of the mean IC
    hit_rate: float | None  # % of months with IC > 0
    spread_annual: float | None  # top minus bottom bucket, annualised %
    bucket_returns: list[float]  # mean monthly % return per bucket, lowest to highest


def summarize(ics: pd.Series, qrets: pd.DataFrame) -> FactorStats:
    n = len(ics)
    if n < 6:
        return FactorStats(n, None, None, None, None, [])
    std = ics.std()
    spread = None
    buckets: list[float] = []
    if not qrets.empty:
        means = qrets.mean()
        buckets = [round(float(v) * 100, 2) for v in means]
        spread_m = (qrets[qrets.columns.max()] - qrets[qrets.columns.min()]).mean()
        spread = round(((1 + spread_m) ** 12 - 1) * 100, 2)
    return FactorStats(
        months=n,
        ic_mean=round(float(ics.mean()), 4),
        ic_t=round(float(ics.mean() / std * np.sqrt(n)), 2) if std > 0 else None,
        hit_rate=round(float((ics > 0).mean() * 100), 1),
        spread_annual=spread,
        bucket_returns=buckets,
    )


def verdict(train: FactorStats, test: FactorStats) -> str:
    """Plain-language evidence label. Deliberately strict: |t| >= 2 in the tuning period and
    the same sign out of sample."""
    if train.ic_t is None or test.ic_mean is None:
        return "Not enough data"
    if abs(train.ic_t) < 2:
        return "No reliable evidence"
    same_sign = np.sign(train.ic_mean) == np.sign(test.ic_mean)
    if not same_sign:
        return "Did not hold out of sample"
    if train.ic_mean < 0:
        return "Worked in reverse"
    return "Held up out of sample" if (test.ic_t or 0) >= 1 else "Weaker out of sample"


@dataclass(frozen=True)
class FactorReport:
    key: str
    full: FactorStats
    train: FactorStats
    test: FactorStats
    verdict: str


def research_factor(key: str, factor: pd.DataFrame, fwd: pd.DataFrame, test_start: pd.Timestamp) -> FactorReport:
    factor_m = factor.reindex(fwd.index)
    ics = information_coefficients(factor_m, fwd)
    stocks = int(fwd.notna().sum(axis=1).median()) if len(fwd) else 0
    buckets = 5 if stocks >= 50 else 3
    qrets = quantile_returns(factor_m, fwd, buckets)
    split = lambda x: (x[x.index < test_start], x[x.index >= test_start])  # noqa: E731
    ic_tr, ic_te = split(ics)
    q_tr, q_te = split(qrets)
    train, test = summarize(ic_tr, q_tr), summarize(ic_te, q_te)
    return FactorReport(key, summarize(ics, qrets), train, test, verdict(train, test))
