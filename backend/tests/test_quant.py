"""Quant engine: no look-ahead, factor maths, research statistics, backtest accounting, API."""

from datetime import date, timedelta
from decimal import Decimal as D

import numpy as np
import pandas as pd
import pytest

from app.models import Instrument, PriceBar
from app.quant import backtest as bt
from app.quant.factors import FACTORS, low_beta, mom_12_1
from app.quant.research import forward_returns, information_coefficients, rebalance_dates, research_factor


def panel(n_stocks=30, years=4, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=252 * years)
    rets = rng.normal(0.0004, 0.015, size=(len(idx), n_stocks))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=[f"S{i:02d}" for i in range(n_stocks)])


def test_factors_never_look_ahead():
    close = panel()
    t = close.index[400]
    base = {k: f.compute(close, close.mean(axis=1)).loc[t] for k, f in FACTORS.items()}
    shocked = close.copy()
    shocked.loc[shocked.index > t] *= 3  # change only the future
    for k, f in FACTORS.items():
        pd.testing.assert_series_equal(f.compute(shocked, shocked.mean(axis=1)).loc[t], base[k], check_names=False)


def test_momentum_skips_the_latest_month():
    close = panel(n_stocks=3)
    i = 300
    expected = close.iloc[i - 21] / close.iloc[i - 252] - 1
    pd.testing.assert_series_equal(mom_12_1(close, None).iloc[i], expected, check_names=False)


def test_low_beta_recovers_known_beta():
    idx = pd.bdate_range("2020-01-01", periods=400)
    b_ret = pd.Series(np.random.default_rng(1).normal(0, 0.01, len(idx)), index=idx)
    bench = 100 * (1 + b_ret).cumprod()
    stock = 100 * (1 + 2 * b_ret).cumprod()
    beta = -low_beta(pd.DataFrame({"X": stock}), bench)["X"].iloc[-1]
    assert beta == pytest.approx(2.0, abs=1e-6)


def test_rebalance_dates_are_month_ends():
    idx = pd.bdate_range("2024-01-01", "2024-03-31")
    assert [d.date() for d in rebalance_dates(idx)] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 29)]


def oracle(close):
    dates = rebalance_dates(close.index)
    fwd = forward_returns(close, dates)
    return dates, fwd, fwd.copy()  # a factor equal to next month's return: perfect foresight


def test_oracle_factor_has_ic_of_one_and_random_factor_does_not():
    close = panel()
    dates, fwd, factor = oracle(close)
    ics = information_coefficients(factor, fwd)
    assert ics.min() == pytest.approx(1.0)
    noisy = factor + np.random.default_rng(5).normal(0, 0.02, factor.shape)  # near-perfect, so IC varies
    rep = research_factor("oracle", noisy, fwd, dates[24])
    assert rep.verdict == "Held up out of sample" and rep.train.spread_annual > 0
    noise = pd.DataFrame(np.random.default_rng(3).normal(size=fwd.shape), index=fwd.index, columns=fwd.columns)
    assert abs(information_coefficients(noise, fwd).mean()) < 0.1


def test_backtest_costs_and_turnover_accounting():
    close = panel()
    dates, fwd, factor = oracle(close)
    res = bt.run_backtest({"o": factor}, {"o": 1}, fwd, None, top_n=5, cost_per_side=0.002)
    assert res.turnover.iloc[0] == 1.0
    assert res.gross.iloc[0] - res.strategy.iloc[0] == pytest.approx(0.002)  # initial buy: one side
    later = res.gross.iloc[1:] - res.strategy.iloc[1:]
    assert np.allclose(later, 2 * 0.002 * res.turnover.iloc[1:])  # rebalance: sell + buy the turnover
    assert (res.strategy > res.equal_weight).mean() > 0.9  # foresight beats the universe
    assert len(res.strategy) == len(dates) - 1  # last date has no forward return


def test_metrics_on_known_returns():
    m = bt.metrics(pd.Series([0.10, -0.50, 0.20]), rf_annual=0.0)
    assert m.total_return == pytest.approx(-34.0)
    assert m.max_drawdown == pytest.approx(-50.0)
    assert bt.metrics(pd.Series([0.01]), 0.0).cagr is None


# ---------------------------------------------------------------- API


def seed_panel(db, n_stocks=30, years=4):
    close = panel(n_stocks, years)
    bench = close.mean(axis=1)
    for sym in list(close.columns) + ["NIFTY50"]:
        inst = Instrument(symbol=sym, name=sym, exchange="NSE", sector="Index" if sym == "NIFTY50" else f"Sec{int(sym[1:] if sym != 'NIFTY50' else 0) % 4}",
                          kind="INDEX" if sym == "NIFTY50" else "EQUITY", data_source="test", data_status="HISTORICAL")
        db.add(inst)
        db.flush()
        series = bench if sym == "NIFTY50" else close[sym]
        db.add_all(PriceBar(instrument_id=inst.id, date=d.date(), open=D(f"{v:.2f}"), high=D(f"{v:.2f}"),
                            low=D(f"{v:.2f}"), close=D(f"{v:.2f}"), volume=1000) for d, v in series.items())
    db.commit()


def test_quant_api(client, db):
    seed_panel(db)
    f = client.get("/api/quant/factors").json()
    assert f["universe_size"] == 30 and f["benchmark"] == "NIFTY50"
    assert {x["key"] for x in f["factors"]} == set(FACTORS)
    assert all(x["verdict"] for x in f["factors"]) and len(f["caveats"]) >= 3

    r = client.post("/api/quant/backtest", json={"weights": {"mom_12_1": 1, "low_vol": 1}, "top_n": 10, "cost_bps": 20})
    assert r.status_code == 200
    b = r.json()
    assert b["curve"][0]["strategy"] == 100.0 and len(b["latest_holdings"]) == 10
    assert b["full"]["strategy"]["months"] == b["train"]["strategy"]["months"] + b["test"]["strategy"]["months"]
    assert b["full"]["vs_equal_weight"]["excess_cagr"] is not None

    s = client.post("/api/quant/screen", json={"weights": {"trend_200": 1}}).json()
    assert [row["rank"] for row in s["rows"]] == list(range(1, len(s["rows"]) + 1))
    assert "not a recommendation" in s["disclaimer"].lower()
    assert "NIFTY50" not in {row["symbol"] for row in s["rows"]}

    bad = client.post("/api/quant/backtest", json={"weights": {"astrology": 1}})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "BAD_FACTORS"
    assert client.post("/api/quant/backtest", json={"weights": {"mom_12_1": -1}}).status_code == 422


def test_index_is_not_tradable_or_listed(client, db):
    seed_panel(db, n_stocks=10, years=1)
    from tests.conftest import add_account
    add_account(db)
    assert "NIFTY50" not in {s["symbol"] for s in client.get("/api/stocks").json()}
    r = client.post("/api/paper-trades", json={"symbol": "NIFTY50", "side": "BUY", "quantity": 1})
    assert r.status_code == 400 and "index" in r.json()["detail"]["message"]


def test_quant_api_needs_data(client, db):
    assert client.get("/api/quant/factors").status_code == 503
