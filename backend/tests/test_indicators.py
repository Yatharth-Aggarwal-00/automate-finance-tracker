import math

import pytest

from app.services.indicators import historical_volatility, rsi, sma


def test_sma_window():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_needs_full_window():
    assert sma([1, 2], 20) == [None, None]


def test_rsi_extremes_and_warmup():
    up = rsi([float(i) for i in range(30)])
    assert up[:14] == [None] * 14
    assert up[14] == 100.0 and up[-1] == 100.0
    down = rsi([float(30 - i) for i in range(30)])
    assert down[-1] == 0.0
    assert rsi([5.0] * 30)[-1] == 50.0


def test_rsi_matches_hand_computed_wilder_value():
    closes = [10.0, 11.0, 10.0, 11.0]  # changes +1, -1, +1
    out = rsi(closes, period=2)
    # seed: gain 0.5, loss 0.5 -> 50; next: gain (0.5+1)/2 = 0.75, loss 0.25 -> RS 3 -> 75
    assert out[2] == pytest.approx(50.0)
    assert out[3] == pytest.approx(75.0)


def test_volatility_zero_for_constant_growth_and_none_when_short():
    closes = [100 * 1.01**i for i in range(30)]
    assert historical_volatility(closes) == pytest.approx(0.0, abs=1e-9)
    assert historical_volatility(closes[:10]) is None


def test_volatility_annualises_daily_std():
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] * math.exp(0.01 if i % 2 else -0.01))
    vol = historical_volatility(closes, 20)
    expected_daily = math.sqrt(sum(0.01**2 for _ in range(20)) / 19)  # mean is 0
    assert vol == pytest.approx(expected_daily * math.sqrt(252) * 100)
