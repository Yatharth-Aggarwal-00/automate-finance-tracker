"""Integration test of the main workflow through the HTTP API."""

import pytest


def test_health(client, db):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["llm_enabled"] is False


def test_full_paper_trading_workflow(client, market):
    stocks = client.get("/api/stocks").json()
    assert [s["symbol"] for s in stocks] == ["AAA", "BBB", "CCC"]
    assert stocks[0]["price"] == 159.0 and stocks[0]["previous_close"] == 158.0
    assert stocks[0]["data_status"] == "SIMULATED" and stocks[0]["as_of"]

    quote = client.get("/api/stocks/aaa/quote").json()
    assert quote["indicators"]["sma20"] == pytest.approx(149.5)
    assert quote["indicators"]["sma50"] == pytest.approx(134.5)
    assert quote["indicators"]["rsi14"] == 100.0

    hist = client.get("/api/stocks/AAA/history", params={"days": 30}).json()
    assert len(hist["candles"]) == 30
    assert hist["candles"][-1]["sma20"] == pytest.approx(149.5)

    p0 = client.get("/api/portfolio").json()
    assert p0["cash"] == 100000.0 and p0["holdings"] == [] and p0["total_value"] == 100000.0

    preview = client.post("/api/paper-trades/preview", json={"symbol": "BBB", "side": "BUY", "quantity": 10}).json()
    assert preview["simulated"] is True
    assert preview["cash_after"] == pytest.approx(100000 - 12950 - 12.95)
    assert client.get("/api/portfolio").json()["cash"] == 100000.0  # preview does not execute

    order = {"symbol": "BBB", "side": "BUY", "quantity": 10}
    r1 = client.post("/api/paper-trades", json=order, headers={"Idempotency-Key": "buy-bbb-0001"})
    assert r1.status_code == 201
    assert r1.json()["order"]["status"] == "EXECUTED" and r1.json()["replayed"] is False
    r2 = client.post("/api/paper-trades", json=order, headers={"Idempotency-Key": "buy-bbb-0001"})
    assert r2.json()["replayed"] is True and r2.json()["order"]["id"] == r1.json()["order"]["id"]

    sell = client.post("/api/paper-trades", json={"symbol": "BBB", "side": "SELL", "quantity": 4})
    assert sell.status_code == 201
    assert sell.json()["order"]["trade"]["realized_pnl"] == pytest.approx(-(5.18 + 5.18), abs=0.01)

    oversell = client.post("/api/paper-trades", json={"symbol": "BBB", "side": "SELL", "quantity": 100})
    assert oversell.status_code == 400
    assert oversell.json()["detail"]["code"] == "INSUFFICIENT_HOLDINGS"

    p = client.get("/api/portfolio").json()
    [h] = p["holdings"]
    assert h["symbol"] == "BBB" and h["quantity"] == 6
    assert p["total_pnl"] == pytest.approx(p["realized_pnl"] + p["unrealized_pnl"], abs=0.005)
    assert p["total_value"] == pytest.approx(p["cash"] + p["market_value"], abs=0.005)

    txns = client.get("/api/portfolio/transactions").json()
    assert [t["side"] for t in txns] == ["SELL", "BUY"]  # replay did not add a trade
    orders = client.get("/api/paper-trades").json()
    assert [o["status"] for o in orders] == ["REJECTED", "EXECUTED", "EXECUTED"]

    history = client.get("/api/portfolio/history").json()
    assert history[-1]["total_value"] == pytest.approx(p["total_value"], abs=0.005)

    insights = client.get("/api/insights").json()
    assert insights["generated_by"] == "rules"
    assert "not a prediction" in insights["disclaimer"]
    assert any(i["kind"] == "sector_concentration" for i in insights["insights"])


@pytest.mark.parametrize(
    "body",
    [
        {"symbol": "AAA", "side": "BUY", "quantity": 0},
        {"symbol": "AAA", "side": "BUY", "quantity": -1},
        {"symbol": "AAA", "side": "BUY", "quantity": 1.5},
        {"symbol": "AAA", "side": "HOLD", "quantity": 1},
        {"symbol": "AAA; DROP TABLE", "side": "BUY", "quantity": 1},
        {"symbol": "AAA", "side": "BUY"},
    ],
)
def test_invalid_orders_rejected_with_422(client, market, body):
    assert client.post("/api/paper-trades", json=body).status_code == 422


def test_unknown_symbol_returns_404(client, market):
    r = client.post("/api/paper-trades", json={"symbol": "ZZZ", "side": "BUY", "quantity": 1})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "UNKNOWN_SYMBOL"
    assert client.get("/api/stocks/ZZZ/quote").status_code == 404


def test_short_idempotency_key_rejected(client, market):
    r = client.post("/api/paper-trades", json={"symbol": "AAA", "side": "BUY", "quantity": 1},
                    headers={"Idempotency-Key": "x"})
    assert r.status_code == 422
