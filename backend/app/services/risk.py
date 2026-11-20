"""Historical risk facts for a price series. Pure functions; they describe the past, not the future."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

TRADING_DAYS_PER_YEAR = 252
TRADING_DAYS_PER_MONTH = 21


@dataclass(frozen=True)
class Drawdown:
    pct: float  # negative, e.g. -38.2
    peak_date: date
    trough_date: date


@dataclass(frozen=True)
class WindowReturn:
    pct: float
    start_date: date
    end_date: date


def max_drawdown(dates: Sequence[date], closes: Sequence[float]) -> Drawdown | None:
    """Largest peak-to-trough fall."""
    if len(closes) < 2:
        return None
    peak_i, best = 0, (0.0, 0, 0)
    for i, c in enumerate(closes):
        if c > closes[peak_i]:
            peak_i = i
        dd = (c / closes[peak_i] - 1) * 100
        if dd < best[0]:
            best = (dd, peak_i, i)
    pct, p, t = best
    return Drawdown(round(pct, 2), dates[p], dates[t]) if pct < 0 else None


def worst_window(dates: Sequence[date], closes: Sequence[float], window: int) -> WindowReturn | None:
    """Worst return over any `window` consecutive trading days."""
    if len(closes) <= window:
        return None
    i = min(range(len(closes) - window), key=lambda j: closes[j + window] / closes[j])
    return WindowReturn(round((closes[i + window] / closes[i] - 1) * 100, 2), dates[i], dates[i + window])


def share_of_losing_windows(closes: Sequence[float], window: int) -> float | None:
    """% of all `window`-day holding periods that ended below their start."""
    n = len(closes) - window
    if n <= 0:
        return None
    losing = sum(1 for j in range(n) if closes[j + window] < closes[j])
    return round(losing / n * 100, 1)


def annual_volatility(closes: Sequence[float], days: int = TRADING_DAYS_PER_YEAR) -> float | None:
    tail = closes[-(days + 1) :]
    if len(tail) < 22:
        return None
    rets = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)
