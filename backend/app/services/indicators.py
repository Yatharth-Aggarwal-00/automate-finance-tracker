"""Technical indicators on daily closes. Informational only."""

import math
from collections.abc import Sequence

TRADING_DAYS_PER_YEAR = 252


def sma(values: Sequence[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI. First value appears at index `period` (needs period + 1 closes)."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_gain = sum(max(c, 0.0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0.0) for c in changes[:period]) / period

    def to_rsi(gain: float, loss: float) -> float:
        if loss == 0:
            return 50.0 if gain == 0 else 100.0
        return 100 - 100 / (1 + gain / loss)

    out[period] = to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        c = changes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(c, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, 0.0)) / period
        out[i] = to_rsi(avg_gain, avg_loss)
    return out


def historical_volatility(values: Sequence[float], window: int = 20) -> float | None:
    """Annualised standard deviation of daily log returns over the last `window` returns, in %."""
    if len(values) < window + 1:
        return None
    tail = values[-(window + 1) :]
    rets = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100


def latest(series: Sequence[float | None]) -> float | None:
    return series[-1] if series else None
