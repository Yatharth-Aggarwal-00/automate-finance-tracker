from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app.models import Holding, PaperOrder, Trade
from app.services.market import UnknownSymbol
from app.services.trading import OrderRejected, get_account, place_order


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_buy_deducts_cash_and_creates_holding(market, settings):
    r = place_order(market, settings, symbol="BBB", side="BUY", quantity=10)
    assert r.order.status == "EXECUTED" and not r.replayed
    assert r.trade.price == D("1295.00")
    assert r.trade.fees == D("12.95")
    acct = get_account(market)
    market.refresh(acct)
    assert acct.cash == D("100000.00") - D("12950.00") - D("12.95")
    h = market.scalar(select(Holding))
    assert (h.quantity, h.cost_basis) == (10, D("12962.95"))


def test_sell_adds_proceeds_and_records_realized_pnl(market, settings):
    place_order(market, settings, symbol="AAA", side="BUY", quantity=20)
    r = place_order(market, settings, symbol="AAA", side="SELL", quantity=20)
    assert r.trade.realized_pnl == D("-6.36")  # only the two estimated charges are lost
    assert count(market, Holding) == 0
    acct = get_account(market)
    market.refresh(acct)
    assert acct.cash == D("100000.00") - D("6.36")


def test_insufficient_cash_is_rejected_and_recorded_without_side_effects(market, settings):
    with pytest.raises(OrderRejected) as exc:
        place_order(market, settings, symbol="BBB", side="BUY", quantity=1000)
    assert exc.value.error.code == "INSUFFICIENT_CASH"
    order = market.get(PaperOrder, exc.value.order.id)
    assert order.status == "REJECTED"
    assert count(market, Trade) == 0 and count(market, Holding) == 0
    assert get_account(market).cash == D("100000.00")


def test_insufficient_holdings_is_rejected(market, settings):
    place_order(market, settings, symbol="CCC", side="BUY", quantity=5)
    with pytest.raises(OrderRejected) as exc:
        place_order(market, settings, symbol="CCC", side="SELL", quantity=6)
    assert exc.value.error.code == "INSUFFICIENT_HOLDINGS"
    assert market.scalar(select(Holding.quantity)) == 5
    assert count(market, Trade) == 1


def test_idempotency_key_prevents_duplicate_trade(market, settings):
    first = place_order(market, settings, symbol="AAA", side="BUY", quantity=3, idempotency_key="key-123456")
    second = place_order(market, settings, symbol="AAA", side="BUY", quantity=3, idempotency_key="key-123456")
    assert second.replayed and second.order.id == first.order.id
    assert count(market, Trade) == 1
    assert market.scalar(select(Holding.quantity)) == 3


def test_unknown_symbol_records_nothing(market, settings):
    with pytest.raises(UnknownSymbol):
        place_order(market, settings, symbol="NOPE", side="BUY", quantity=1)
    assert count(market, PaperOrder) == 0


def test_cash_never_goes_negative_at_exact_boundary(market, settings):
    # 77 x 1295 = 99,715 + 99.72 fees = 99,814.72 <= 1,00,000; 78 would exceed.
    place_order(market, settings, symbol="BBB", side="BUY", quantity=77)
    with pytest.raises(OrderRejected):
        place_order(market, settings, symbol="BBB", side="BUY", quantity=1)  # needs 1,296.30 > 185.28
    acct = get_account(market)
    market.refresh(acct)
    assert acct.cash == D("185.28")
