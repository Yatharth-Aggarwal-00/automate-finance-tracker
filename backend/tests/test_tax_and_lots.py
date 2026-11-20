from datetime import date
from decimal import Decimal as D

import pytest

from app.services.lots import LedgerTrade, Lot, consume_fifo, replay
from app.services.risk import annual_volatility, max_drawdown, share_of_losing_windows, worst_window
from app.services.tax import (
    RealizedGain,
    estimate_tax,
    financial_year,
    fy_label,
    is_long_term,
    long_term_from,
)


def gain(amount, long_term: bool, sell=date(2026, 6, 1)):
    buy = date(2025, 1, 1) if long_term else date(2026, 1, 1)
    return RealizedGain("X", buy, sell, 1, D("0"), D(str(amount)))


def test_long_term_needs_more_than_12_months():
    assert long_term_from(date(2025, 11, 19)) == date(2026, 11, 20)
    assert not is_long_term(date(2025, 11, 19), date(2026, 11, 19))
    assert is_long_term(date(2025, 11, 19), date(2026, 11, 20))


def test_long_term_from_leap_day():
    assert long_term_from(date(2024, 2, 29)) == date(2025, 3, 1)


@pytest.mark.parametrize(
    "d,fy",
    [(date(2026, 3, 31), "FY 2025-26"), (date(2026, 4, 1), "FY 2026-27"), (date(2026, 11, 19), "FY 2026-27")],
)
def test_financial_year(d, fy):
    assert fy_label(d) == fy
    start, end = financial_year(d)
    assert start <= d <= end and start.month == 4 and end.month == 3


def test_short_term_gain_taxed_at_20_pct_plus_cess():
    e = estimate_tax([gain(100000, long_term=False)])
    assert e.tax == D("20800.00")
    assert e.exemption_remaining == D("125000.00")


def test_long_term_gain_uses_exemption_first():
    assert estimate_tax([gain(100000, long_term=True)]).tax == D("0.00")
    e = estimate_tax([gain(200000, long_term=True)])
    assert e.taxable_long_term == D("75000")
    assert e.tax == D("9750.00")  # 75,000 x 12.5% x 1.04
    assert e.exemption_remaining == D("0.00")


def test_short_term_loss_offsets_long_term_gain():
    e = estimate_tax([gain(-50000, long_term=False), gain(200000, long_term=True)])
    assert e.long_term_net == D("150000") and e.tax == D("3250.00")


def test_long_term_loss_cannot_offset_short_term_gain():
    e = estimate_tax([gain(-50000, long_term=True), gain(100000, long_term=False)])
    assert e.tax == D("20800.00")


def test_fifo_consumes_oldest_lots_and_splits_proceeds_exactly():
    lots = [Lot("X", date(2024, 1, 1), 10, D("1000.00")), Lot("X", date(2025, 6, 1), 10, D("2000.00"))]
    remaining, pieces = consume_fifo(lots, 15, date(2026, 1, 1), D("3000.00"))
    assert [(p.quantity, p.cost, p.proceeds, p.long_term) for p in pieces] == [
        (10, D("1000.00"), D("2000.00"), True),
        (5, D("1000.00"), D("1000.00"), False),
    ]
    assert remaining == [Lot("X", date(2025, 6, 1), 5, D("1000.00"))]
    _, odd = consume_fifo([Lot("X", date(2024, 1, 1), 3, D("10.00"))] * 3, 7, date(2026, 1, 1), D("100.00"))
    assert sum(p.proceeds for p in odd) == D("100.00")


def test_fifo_rejects_overselling():
    with pytest.raises(ValueError):
        consume_fifo([Lot("X", date(2024, 1, 1), 1, D("1"))], 2, date(2026, 1, 1), D("5"))


def test_replay_builds_lots_and_realized_gains():
    trades = [
        LedgerTrade("X", "BUY", 10, date(2024, 1, 1), D("-1000.00")),
        LedgerTrade("X", "BUY", 10, date(2025, 6, 1), D("-2000.00")),
        LedgerTrade("Y", "BUY", 5, date(2025, 6, 1), D("-500.00")),
        LedgerTrade("Y", "SELL", 5, date(2025, 7, 1), D("450.00")),
        LedgerTrade("X", "SELL", 12, date(2026, 1, 1), D("2400.00")),
    ]
    lots, realized = replay(trades)
    assert list(lots) == ["X"] and lots["X"][0].quantity == 8
    assert [round(g.gain) for g in realized] == [-50, 1000, 0]


def test_risk_facts():
    days = [date(2026, 1, d) for d in range(1, 6)]
    dd = max_drawdown(days, [100, 120, 60, 90, 130])
    assert (dd.pct, dd.peak_date, dd.trough_date) == (-50.0, days[1], days[2])
    assert max_drawdown(days[:3], [1, 2, 3]) is None
    assert worst_window(days[:3], [100, 90, 99], 1).pct == -10.0
    assert share_of_losing_windows([100, 90, 99, 80], 1) == pytest.approx(66.7)
    assert annual_volatility([100.0] * 10) is None
