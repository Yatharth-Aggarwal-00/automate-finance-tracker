import csv
from datetime import date, datetime, time
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.base import Candle, DataStatus, InstrumentInfo, MarketDataUnavailable, Quote

IST = ZoneInfo("Asia/Kolkata")
# NSE equity close. EOD candles are stamped at the close of their trading day.
MARKET_CLOSE = time(15, 30)


def eod_timestamp(d: date) -> datetime:
    return datetime.combine(d, MARKET_CLOSE, tzinfo=IST)


class CsvProvider:
    """Reads `instruments.csv` and one `<SYMBOL>.csv` of daily OHLCV per instrument.

    The bundled fixtures are generated (see scripts/generate_fixtures.py), so the
    default status is SIMULATED. Point MARKET_DATA_DIR at real EOD files you are
    licensed to use and set CSV_DATA_STATUS=HISTORICAL to relabel them.
    """

    source = "csv"

    def __init__(self, data_dir: Path, status: DataStatus = DataStatus.SIMULATED):
        self.data_dir = Path(data_dir)
        self.status = DataStatus(status)

    @cached_property
    def _instruments(self) -> dict[str, InstrumentInfo]:
        path = self.data_dir / "instruments.csv"
        if not path.exists():
            raise MarketDataUnavailable(f"Instrument list not found: {path}")
        with path.open(newline="", encoding="utf-8") as f:
            rows = [InstrumentInfo(r["symbol"], r["name"], r["exchange"], r["sector"]) for r in csv.DictReader(f)]
        return {r.symbol: r for r in rows}

    def list_instruments(self, query: str | None = None) -> list[InstrumentInfo]:
        items = list(self._instruments.values())
        if query:
            q = query.strip().lower()
            items = [i for i in items if q in i.symbol.lower() or q in i.name.lower()]
        return items

    def get_history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Candle]:
        if symbol not in self._instruments:
            raise MarketDataUnavailable(f"Unknown symbol: {symbol}")
        path = self.data_dir / f"{symbol}.csv"
        if not path.exists():
            raise MarketDataUnavailable(f"No price history file for {symbol}")
        with path.open(newline="", encoding="utf-8") as f:
            candles = [
                Candle(
                    date=date.fromisoformat(r["date"]),
                    open=Decimal(r["open"]),
                    high=Decimal(r["high"]),
                    low=Decimal(r["low"]),
                    close=Decimal(r["close"]),
                    volume=int(r["volume"]),
                )
                for r in csv.DictReader(f)
            ]
        candles.sort(key=lambda c: c.date)
        return [c for c in candles if (start is None or c.date >= start) and (end is None or c.date <= end)]

    def get_quote(self, symbol: str) -> Quote:
        candles = self.get_history(symbol)
        if not candles:
            raise MarketDataUnavailable(f"No prices for {symbol}")
        last = candles[-1]
        prev = candles[-2].close if len(candles) > 1 else None
        return Quote(symbol, last.close, prev, eod_timestamp(last.date), self.source, self.status)
