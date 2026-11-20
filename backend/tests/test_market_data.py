"""Yahoo provider parsing, source switching in sync, and seed fallbacks. No network access."""

from datetime import date, datetime
from decimal import Decimal as D

import pandas as pd
import pytest
from sqlalchemy import func, select

from app.market.base import MarketDataUnavailable
from app.market.sync import sync_market_data
from app.market.yahoo_provider import IST, YahooProvider, yahoo_ticker
from app.models import Instrument, PriceBar, Trade
from scripts.seed import DEMO_TRADES, seed
from tests.conftest import add_instrument, make_settings

UNIVERSE = "symbol,name,exchange,sector\nAAA,Aaa Ltd,NSE,Energy\nM&M,Mahindra & Mahindra Ltd,NSE,Automobile\nGONE,Gone Ltd,NSE,Energy\n"


def yahoo_frame(data: dict[str, list[tuple]]) -> pd.DataFrame:
    """Build the MultiIndex (ticker, field) frame yfinance.download(group_by='ticker') returns."""
    parts = {}
    for ticker, rows in data.items():
        parts[ticker] = pd.DataFrame(
            {
                "Open": [r[1] for r in rows],
                "High": [r[2] for r in rows],
                "Low": [r[3] for r in rows],
                "Close": [r[4] for r in rows],
                "Adj Close": [r[4] for r in rows],
                "Volume": [r[5] for r in rows],
            },
            index=pd.DatetimeIndex([r[0] for r in rows]),
        )
    return pd.concat(parts, axis=1)


FRAME = yahoo_frame(
    {
        "AAA.NS": [
            ("2026-11-12", 100, 102, 99, 101.005, 1000),
            ("2026-11-13", float("nan"), float("nan"), float("nan"), float("nan"), float("nan")),  # holiday gap
            ("2026-11-16", 101, 104, 100, 103.5, 2000),
            ("2026-11-17", 103, 105, 102, 104.0, 500),  # today's session
        ],
        "M&M.NS": [
            ("2026-11-12", 3000, 3010, 2990, 3005, 10),
            ("2026-11-16", 3005, 3020, 3000, 3010, float("nan")),
            ("2026-11-17", 3010, 3030, 3000, 3020, 20),
        ],
    }
)


@pytest.fixture
def universe(tmp_path):
    f = tmp_path / "universe.csv"
    f.write_text(UNIVERSE, encoding="utf-8")
    return f


def provider(universe, frame=FRAME, now=datetime(2026, 11, 17, 18, 0, tzinfo=IST)):
    p = YahooProvider(universe, date(2015, 1, 1), now=now)
    p._download = lambda tickers: frame if not isinstance(frame, Exception) else (_ for _ in ()).throw(frame)
    return p


def test_ticker_mapping():
    assert yahoo_ticker("M&M", "NSE") == "M&M.NS"
    assert yahoo_ticker("RELIANCE", "BSE") == "RELIANCE.BO"


def test_parses_candles_skips_gaps_and_missing_tickers(universe):
    p = provider(universe)
    assert [i.symbol for i in p.list_instruments()] == ["AAA", "M&M"]  # GONE has no data
    aaa = p.get_history("AAA")
    assert [c.date for c in aaa] == [date(2026, 11, 12), date(2026, 11, 16), date(2026, 11, 17)]
    assert aaa[0].close == D("101.01")  # rounded half-up to the paisa
    assert p.get_history("M&M")[1].volume == 0  # NaN volume -> 0
    q = p.get_quote("AAA")
    assert (q.price, q.previous_close, q.status.value) == (D("104.00"), D("103.50"), "HISTORICAL")


def test_drops_in_progress_bar_during_market_hours(universe):
    p = provider(universe, now=datetime(2026, 11, 17, 11, 30, tzinfo=IST))
    assert p.get_history("AAA")[-1].date == date(2026, 11, 16)


@pytest.mark.parametrize("bad", [RuntimeError("rate limited"), pd.DataFrame()])
def test_download_failure_raises_unavailable(universe, bad):
    with pytest.raises(MarketDataUnavailable):
        provider(universe, frame=bad).list_instruments()


def test_sync_replaces_bars_when_source_changes(db, universe):
    add_instrument(db, "AAA", ["50", "51", "52"], end=date(2026, 1, 3))  # source "test"
    sync_market_data(db, provider(universe))
    inst = db.scalar(select(Instrument).where(Instrument.symbol == "AAA"))
    dates = list(db.scalars(select(PriceBar.date).where(PriceBar.instrument_id == inst.id).order_by(PriceBar.date)))
    assert inst.data_source == "yahoo" and inst.data_status == "HISTORICAL"
    assert dates == [date(2026, 11, 12), date(2026, 11, 16), date(2026, 11, 17)]  # old test bars gone
    # Re-sync from the same source upserts without duplicates.
    sync_market_data(db, provider(universe))
    assert db.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.instrument_id == inst.id)) == 3


def test_seed_falls_back_to_simulated_data_when_provider_fails_on_empty_db(db, monkeypatch):
    monkeypatch.setattr(YahooProvider, "_download", lambda self, t: (_ for _ in ()).throw(RuntimeError("offline")))
    msg = seed(db, make_settings(market_data_provider="yahoo"))
    assert "SIMULATED" in msg and "offline" in msg
    assert set(db.scalars(select(Instrument.data_status))) == {"SIMULATED"}
    assert db.scalar(select(func.count()).select_from(Trade)) == len(DEMO_TRADES)


def test_seed_keeps_existing_prices_when_provider_fails(db, monkeypatch):
    add_instrument(db, "AAA", ["50", "51"])
    monkeypatch.setattr(YahooProvider, "_download", lambda self, t: (_ for _ in ()).throw(RuntimeError("offline")))
    msg = seed(db, make_settings(market_data_provider="yahoo"), demo_trades=False)
    assert "Keeping the existing price data" in msg
    assert db.scalar(select(func.count()).select_from(PriceBar)) == 2
