"""Decision checks and tax summary through the API, with a fixed 'today'."""

from datetime import date, datetime
from decimal import Decimal as D

import pytest

from app.market.yahoo_provider import IST
from app.services import checks
from app.services.trading import place_order

TODAY = date(2026, 11, 19)  # FY 2026-27


@pytest.fixture
def held(market, settings, monkeypatch):
    """10 AAA bought on 1 Dec 2025 at ₹100 (short-term until 2 Dec 2026, 13 days away). AAA now ₹159."""
    monkeypatch.setattr(checks, "today_ist", lambda: TODAY)
    place_order(market, settings, symbol="AAA", side="BUY", quantity=10, fill=(D("100.00"), date(2025, 12, 1)),
                executed_at=datetime(2025, 12, 1, 15, 30, tzinfo=IST))
    return market


def test_sell_check_shows_tax_and_cheaper_wait_option(client, held):
    r = client.post("/api/checks/sell", json={"symbol": "aaa", "quantity": 10})
    assert r.status_code == 200
    c = r.json()
    assert c["fy"] == "FY 2026-27"
    [piece] = c["pieces"]
    assert piece["long_term"] is False and piece["long_term_from"] == "2026-12-02"
    # cost 1,000 + ₹1.00 charges; proceeds 1,590 - ₹1.59 charges
    assert c["gain"] == pytest.approx(587.41)
    assert c["tax"] == pytest.approx(122.18)  # 587.41 x 20% x 1.04
    [wait] = c["options"]
    assert wait["sell_date"] == "2026-12-02" and wait["tax"] == 0.0  # within the ₹1.25 lakh exemption
    assert wait["saving"] == pytest.approx(122.18)


def test_sell_check_explains_short_term_loss_timing(client, held, settings):
    place_order(held, settings, symbol="CCC", side="BUY", quantity=10, fill=(D("500.00"), date(2025, 12, 1)),
                executed_at=datetime(2025, 12, 1, 15, 30, tzinfo=IST))
    c = client.post("/api/checks/sell", json={"symbol": "CCC", "quantity": 10}).json()
    assert c["gain"] < 0 and c["tax"] == 0.0 and c["options"] == []
    assert "short-term loss" in c["notes"][0] and "02 Dec 2026" in c["notes"][0]
    assert "carried forward" in c["notes"][1]


def test_sell_check_rejects_overselling(client, held):
    r = client.post("/api/checks/sell", json={"symbol": "AAA", "quantity": 11})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "INSUFFICIENT_HOLDINGS"


def test_buy_check_flags_concentration(client, held):
    c = client.post("/api/checks/buy", json={"symbol": "CCC", "quantity": 100}).json()
    assert c["max_drawdown_pct"] == pytest.approx(-11.8)  # 500 -> 441
    assert c["max_drawdown_rupees"] < 0
    assert c["sector"] == "Financial Services" and c["position_pct_after"] > 20
    texts = " ".join(f["text"] for f in c["flags"])
    assert "CCC would be" in texts and "Financial Services would be" in texts
    assert "not a recommendation" in c["disclaimer"]


def test_buy_check_reports_insufficient_cash(client, held):
    r = client.post("/api/checks/buy", json={"symbol": "BBB", "quantity": 1000})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "INSUFFICIENT_CASH"


def test_tax_summary_lists_lots_turning_long_term(client, held, settings):
    place_order(held, settings, symbol="AAA", side="SELL", quantity=2)  # realized short-term gain this FY
    s = client.get("/api/tax/summary").json()
    assert s["fy"] == "FY 2026-27" and s["days_left_in_fy"] == 132
    assert s["estimate"]["short_term_net"] > 0 and s["estimate"]["tax"] > 0
    [lot] = s["lots"]
    assert lot["quantity"] == 8 and lot["days_to_long_term"] == 13
    assert lot["extra_tax_if_sold_today"] > 0
    assert s["harvestable_ltcg"] == 0  # nothing long-term yet
    assert s["rates"]["stcg_pct"] == 20.0
