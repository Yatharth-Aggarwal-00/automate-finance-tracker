from datetime import date
from decimal import Decimal as D

import pytest

from app.services.portfolio import (
    InsufficientCash,
    InsufficientHoldings,
    LedgerEntry,
    Position,
    TradingError,
    calculate_order,
    estimate_fees,
    inr,
    portfolio_history,
    summarize,
)

PCT, FLAT = D("0.10"), D("0.00")


def buy(qty, price, cash=D("100000.00"), pos=None, pct=PCT, flat=FLAT):
    return calculate_order("BUY", qty, D(price), cash, pos, pct, flat)


def sell(qty, price, pos, cash=D("0.00"), pct=PCT, flat=FLAT):
    return calculate_order("SELL", qty, D(price), cash, pos, pct, flat)


def test_fee_estimate_percent_plus_flat_rounded_to_paisa():
    assert estimate_fees(D("10000.00"), D("0.10"), D("0")) == D("10.00")
    assert estimate_fees(D("1234.56"), D("0.03"), D("20")) == D("20.37")


def test_buy_deducts_gross_plus_fees_and_adds_to_cost_basis():
    c = buy(10, "1500.00")
    assert c.gross_amount == D("15000.00")
    assert c.fees == D("15.00")
    assert c.cash_change == D("-15015.00")
    assert c.cash_after == D("84985.00")
    assert c.position_after == Position(10, D("15015.00"))
    assert c.position_after.avg_cost == D("1501.50")
    assert c.realized_pnl is None


def test_second_buy_updates_weighted_average_cost():
    first = buy(10, "100.00", pct=D("0"))
    second = buy(10, "200.00", cash=first.cash_after, pos=first.position_after, pct=D("0"))
    assert second.position_after == Position(20, D("3000.00"))
    assert second.position_after.avg_cost == D("150.00")


def test_partial_sell_realizes_pnl_against_proportional_cost():
    pos = Position(10, D("1000.00"))  # avg 100
    c = sell(4, "150.00", pos, pct=D("0"))
    assert c.cash_change == D("600.00")
    assert c.realized_pnl == D("200.00")
    assert c.position_after == Position(6, D("600.00"))


def test_sell_fees_reduce_realized_pnl():
    c = sell(10, "110.00", Position(10, D("1000.00")))
    assert c.fees == D("1.10")
    assert c.cash_change == D("1098.90")
    assert c.realized_pnl == D("98.90")


def test_full_sell_closes_position_and_releases_entire_cost_basis():
    # Cost basis that does not divide evenly; full sell must still remove it exactly.
    pos = Position(3, D("100.00"))
    c = sell(3, "40.00", pos, pct=D("0"))
    assert c.position_after is None
    assert c.realized_pnl == D("20.00")


def test_buy_rejected_when_cash_insufficient_including_fees():
    with pytest.raises(InsufficientCash):
        buy(100, "1000.00", cash=D("100000.00"))  # 1,00,000 + ₹100 fees
    assert buy(100, "1000.00", cash=D("100100.00")).cash_after == D("0.00")


def test_sell_rejected_without_enough_shares():
    with pytest.raises(InsufficientHoldings):
        sell(1, "100.00", None)
    with pytest.raises(InsufficientHoldings):
        sell(11, "100.00", Position(10, D("1000.00")))


@pytest.mark.parametrize("qty", [0, -5])
def test_non_positive_quantity_rejected(qty):
    with pytest.raises(TradingError):
        buy(qty, "100.00")


def test_unknown_side_rejected():
    with pytest.raises(TradingError):
        calculate_order("SHORT", 1, D("100"), D("1000"), None, PCT, FLAT)


def test_total_pnl_equals_realized_plus_unrealized_after_mixed_trades():
    initial = D("100000.00")
    cash, pos, realized = initial, None, D("0")
    for side, qty, price in [("BUY", 7, "333.33"), ("BUY", 5, "401.17"), ("SELL", 4, "389.99"),
                             ("BUY", 3, "377.77"), ("SELL", 6, "420.01")]:
        c = calculate_order(side, qty, D(price), cash, pos, D("0.37"), D("3.00"))
        cash, pos = c.cash_after, c.position_after
        realized += c.realized_pnl or 0
    s = summarize(initial, cash, [("X", pos, D("415.55"))], realized)
    assert s.total_pnl == s.realized_pnl + s.unrealized_pnl
    assert s.total_value == cash + s.market_value
    assert s.invested == pos.cost_basis


def test_summary_return_pct():
    s = summarize(D("100000.00"), D("50000.00"), [("X", Position(100, D("50000.00")), D("550.00"))], D("0"))
    assert s.market_value == D("55000.00")
    assert s.unrealized_pnl == D("5000.00")
    assert s.return_pct == D("5.00")
    assert s.holdings[0].unrealized_pnl_pct == D("10.00")


def test_portfolio_history_replays_ledger_and_carries_closes_forward():
    d1, d2, d3 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)
    ledger = [LedgerEntry(d2, "X", "BUY", 10, D("-1000.00"))]
    closes = {"X": {d1: D("90"), d2: D("100")}}  # no bar on d3 -> carry 100 forward
    pts = portfolio_history(D("5000.00"), ledger, closes, [d1, d2, d3])
    assert [p.total_value for p in pts] == [D("5000.00"), D("5000.00"), D("5000.00")]
    assert pts[1].cash == D("4000.00") and pts[1].market_value == D("1000.00")


def test_inr_uses_indian_digit_grouping():
    assert inr(D("100000")) == "₹1,00,000.00"
    assert inr(D("12345678.9")) == "₹1,23,45,678.90"
    assert inr(D("999")) == "₹999.00"
    assert inr(D("-1500.5")) == "-₹1,500.50"
