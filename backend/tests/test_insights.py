from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.services import insights as svc
from app.services.insights import Insight, llm_summary, rule_based_insights
from tests.conftest import make_settings


def metrics(**overrides):
    base = {
        "initial_cash": 100000.0,
        "total_value": 104000.0,
        "cash": 30000.0,
        "cash_pct_of_portfolio": 28.8,
        "invested_cost_basis": 70000.0,
        "holdings_market_value": 74000.0,
        "unrealized_pnl": 4000.0,
        "realized_pnl": 0.0,
        "total_pnl": 4000.0,
        "return_pct": 4.0,
        "holding_count": 2,
        "sectors": [
            {"sector": "Information Technology", "market_value": 50000.0, "weight_pct_of_holdings": 67.6,
             "weight_pct_of_portfolio": 48.1},
            {"sector": "Energy", "market_value": 24000.0, "weight_pct_of_holdings": 32.4,
             "weight_pct_of_portfolio": 23.1},
        ],
        "holdings": [
            {"symbol": "TCS", "sector": "Information Technology", "quantity": 10, "price": 5000.0,
             "market_value": 50000.0, "weight_pct_of_portfolio": 48.1, "unrealized_pnl": 3000.0,
             "unrealized_pnl_pct": 6.4, "sma20": 4900.0, "sma50": 4600.0, "rsi14": 74.0,
             "volatility_20d_annualised_pct": 18.0},
            {"symbol": "RELIANCE", "sector": "Energy", "quantity": 20, "price": 1200.0, "market_value": 24000.0,
             "weight_pct_of_portfolio": 23.1, "unrealized_pnl": 1000.0, "unrealized_pnl_pct": 4.3,
             "sma20": 1190.0, "sma50": 1180.0, "rsi14": 55.0, "volatility_20d_annualised_pct": 40.0},
        ],
    }
    return base | overrides


def test_rules_flag_sector_and_stock_concentration_rsi_trend_and_volatility():
    out = rule_based_insights(metrics())
    kinds = [i.kind for i in out]
    assert kinds[0] == "performance"
    assert "sector_concentration" in kinds and "single_stock" in kinds
    conc = next(i for i in out if i.kind == "sector_concentration")
    assert "concentrated in the Information Technology sector" in conc.text
    assert any(i.kind == "rsi" and i.symbols == ["TCS"] for i in out)
    assert any(i.kind == "trend" and i.symbols == ["TCS"] for i in out)  # 8.7% above SMA50
    assert any(i.kind == "volatility" and i.symbols == ["RELIANCE"] for i in out)


def test_rules_are_deterministic():
    assert rule_based_insights(metrics()) == rule_based_insights(metrics())


def test_rules_for_all_cash_portfolio():
    out = rule_based_insights(metrics(holding_count=0, sectors=[], holdings=[], total_pnl=0.0, return_pct=0.0,
                                      unrealized_pnl=0.0))
    assert [i.kind for i in out] == ["performance", "cash"]


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fake_client(monkeypatch, result) -> FakeMessages:
    messages = FakeMessages(result)
    monkeypatch.setattr(svc.anthropic, "Anthropic", lambda **_: SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    svc._summary_cache.clear()
    return messages


LLM_SETTINGS = make_settings(anthropic_api_key="sk-test-placeholder")
OBS = [Insight("performance", "info", "t", "x")]


def test_llm_summary_success_sends_only_metrics(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Summary.")])
    msgs = fake_client(monkeypatch, resp)
    assert llm_summary(metrics(), OBS, LLM_SETTINGS) == ("Summary.", None)
    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert "Do not introduce prices" in call["system"]
    # Cached on identical metrics: no second API call.
    llm_summary(metrics(), OBS, LLM_SETTINGS)
    assert len(msgs.calls) == 1


def test_llm_connection_error_falls_back(monkeypatch):
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client(monkeypatch, err)
    summary, error = llm_summary(metrics(), OBS, LLM_SETTINGS)
    assert summary is None and "Could not reach" in error


def test_llm_refusal_falls_back(monkeypatch):
    fake_client(monkeypatch, SimpleNamespace(stop_reason="refusal", content=[]))
    assert llm_summary(metrics(), OBS, LLM_SETTINGS)[0] is None


@pytest.mark.parametrize("model,expects_fallback", [("claude-haiku-5-5", False), ("claude-sonnet-5-5", True)])
def test_fallback_param_only_for_supported_models(monkeypatch, model, expects_fallback):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="ok")])
    msgs = fake_client(monkeypatch, resp)
    llm_summary(metrics(), OBS, make_settings(anthropic_api_key="sk-test", anthropic_model=model))
    assert ("fallbacks" in msgs.calls[0]) is expects_fallback


def test_insights_endpoint_uses_llm_when_configured(client, market, settings, monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Plain summary.")])
    fake_client(monkeypatch, resp)
    settings.anthropic_api_key = "sk-test-placeholder"
    client.post("/api/paper-trades", json={"symbol": "AAA", "side": "BUY", "quantity": 5})
    body = client.get("/api/insights").json()
    assert body["generated_by"] == "rules+llm"
    assert body["summary"] == "Plain summary."
    assert body["insights"]  # rule-based items are always included
