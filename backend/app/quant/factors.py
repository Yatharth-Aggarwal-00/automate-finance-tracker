"""Price-based factor library.

Every factor is a daily panel (dates x symbols) where the value on date t uses only prices up
to and including t, so sampling it at a rebalance date never looks ahead. Higher values are
the "long" side: each factor is oriented so that the published hypothesis predicts higher
future returns for higher values (e.g. low volatility is stored as negative volatility).
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

D_MONTH, D_6M, D_YEAR = 21, 126, 252


@dataclass(frozen=True)
class Factor:
    key: str
    name: str
    description: str
    hypothesis: str
    compute: Callable[[pd.DataFrame, pd.Series | None], pd.DataFrame]
    needs_benchmark: bool = False


def _ret(close: pd.DataFrame) -> pd.DataFrame:
    return close.pct_change(fill_method=None)


def mom_12_1(close, _bench):
    return close.shift(D_MONTH) / close.shift(D_YEAR) - 1


def mom_6_1(close, _bench):
    return close.shift(D_MONTH) / close.shift(D_6M) - 1


def reversal_1m(close, _bench):
    return -(close / close.shift(D_MONTH) - 1)


def low_vol(close, _bench):
    return -_ret(close).rolling(D_YEAR, min_periods=200).std() * np.sqrt(D_YEAR)


def trend_200(close, _bench):
    return close / close.rolling(200, min_periods=200).mean() - 1


def high_52w(close, _bench):
    return close / close.rolling(D_YEAR, min_periods=200).max() - 1


def low_beta(close, bench):
    r = _ret(close)
    b = bench.pct_change(fill_method=None)
    roll = lambda x: x.rolling(D_YEAR, min_periods=200).mean()  # noqa: E731
    cov = roll(r.mul(b, axis=0)).sub(roll(r).mul(roll(b), axis=0))
    var = roll(b * b) - roll(b) ** 2
    return -cov.div(var, axis=0)


FACTORS: dict[str, Factor] = {
    f.key: f
    for f in [
        Factor("mom_12_1", "Momentum 12-1", "Return over the past 12 months, skipping the latest month.",
               "Stocks that rose most over the past year tend to keep outperforming for a while.", mom_12_1),
        Factor("mom_6_1", "Momentum 6-1", "Return over the past 6 months, skipping the latest month.",
               "A shorter-horizon version of momentum.", mom_6_1),
        Factor("reversal_1m", "Short-term reversal", "Negative of the latest 1-month return.",
               "Last month's biggest losers tend to bounce back next month.", reversal_1m),
        Factor("low_vol", "Low volatility", "Negative of annualised daily volatility over the past year.",
               "Calmer stocks have delivered better risk-adjusted returns than their risk suggests.", low_vol),
        Factor("trend_200", "Trend", "Price relative to its 200-day average.",
               "Stocks above their long-term average tend to keep trending.", trend_200),
        Factor("high_52w", "52-week high", "Price relative to its 52-week high (0 = at the high).",
               "Stocks near their 52-week high tend to keep outperforming.", high_52w),
        Factor("low_beta", "Low beta", "Negative of 1-year beta to the Nifty 50.",
               "Low-beta stocks have historically earned more than their market sensitivity implies.",
               low_beta, needs_benchmark=True),
    ]
}


def available(bench: pd.Series | None) -> dict[str, Factor]:
    return {k: f for k, f in FACTORS.items() if bench is not None or not f.needs_benchmark}


def compute_all(close: pd.DataFrame, bench: pd.Series | None) -> dict[str, pd.DataFrame]:
    return {k: f.compute(close, bench) for k, f in available(bench).items()}
