"""Yahoo Finance end-of-day data via the `yfinance` library.

UNOFFICIAL: yfinance scrapes Yahoo's public endpoints, has no SLA, and its README
limits use to research and education. It is fine for personal experiments; swap
it for a licensed broker/data API before building anything for other people.

Prices are split-adjusted closes as Yahoo reports them (not dividend-adjusted).
"""

import csv
import warnings
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.base import Candle, DataStatus, InstrumentInfo, MarketDataUnavailable, Quote
from app.market.csv_provider import eod_timestamp

IST = ZoneInfo("Asia/Kolkata")
# Treat today's bar as final only after the close plus a buffer; before that it is intraday.
EOD_FINAL_AFTER = time(16, 0)
PAISA = Decimal("0.01")


# Benchmarks loaded alongside the universe: (symbol, name, Yahoo ticker).
BENCHMARKS = [("NIFTY50", "Nifty 50 Index", "^NSEI")]
_INDEX_TICKERS = {s: t for s, _, t in BENCHMARKS}


def yahoo_ticker(symbol: str, exchange: str) -> str:
    if symbol in _INDEX_TICKERS:
        return _INDEX_TICKERS[symbol]
    return f"{symbol}.{'BO' if exchange == 'BSE' else 'NS'}"


def _price(x) -> Decimal:
    return Decimal(str(float(x))).quantize(PAISA, rounding=ROUND_HALF_UP)


class YahooProvider:
    source = "yahoo"
    status = DataStatus.HISTORICAL

    def __init__(self, universe_file: Path, start: date, now: datetime | None = None):
        self.universe_file = Path(universe_file)
        self.start = start
        self._now = now  # injectable for tests

    @cached_property
    def _instruments(self) -> dict[str, InstrumentInfo]:
        if not self.universe_file.exists():
            raise MarketDataUnavailable(f"Universe file not found: {self.universe_file}")
        with self.universe_file.open(newline="", encoding="utf-8") as f:
            rows = [InstrumentInfo(r["symbol"], r["name"], r["exchange"], r["sector"]) for r in csv.DictReader(f)]
        rows += [InstrumentInfo(s, n, "NSE", "Index", kind="INDEX") for s, n, _ in BENCHMARKS]
        return {r.symbol: r for r in rows}

    def list_instruments(self, query: str | None = None) -> list[InstrumentInfo]:
        items = [i for i in self._instruments.values() if i.symbol in self._candles]
        if query:
            q = query.strip().lower()
            items = [i for i in items if q in i.symbol.lower() or q in i.name.lower()]
        return items

    def _download(self, tickers: list[str]):
        import yfinance as yf

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return yf.download(
                tickers,
                start=self.start.isoformat(),
                auto_adjust=False,
                group_by="ticker",
                progress=False,
                threads=True,
            )

    @cached_property
    def _candles(self) -> dict[str, list[Candle]]:
        """One batched download for the whole universe, cached for this provider instance."""
        tickers = {yahoo_ticker(i.symbol, i.exchange): i.symbol for i in self._instruments.values()}
        try:
            df = self._download(list(tickers))
        except Exception as e:  # network errors, Yahoo rate limits, parser breakage
            raise MarketDataUnavailable(f"Yahoo Finance download failed: {e}") from e
        if df is None or df.empty:
            raise MarketDataUnavailable("Yahoo Finance returned no data (offline or rate-limited?)")

        now = self._now or datetime.now(IST)
        out: dict[str, list[Candle]] = {}
        for ticker, symbol in tickers.items():
            if ticker not in df.columns.get_level_values(0):
                continue
            frame = df[ticker].dropna(subset=["Open", "High", "Low", "Close"])
            candles = [
                Candle(
                    date=ts.date(),
                    open=_price(row["Open"]),
                    high=_price(row["High"]),
                    low=_price(row["Low"]),
                    close=_price(row["Close"]),
                    volume=int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,  # NaN check
                )
                for ts, row in frame.iterrows()
            ]
            if candles and candles[-1].date == now.date() and now.time() < EOD_FINAL_AFTER:
                candles.pop()  # in-progress session, not an end-of-day close yet
            if candles:
                out[symbol] = candles
        if not out:
            raise MarketDataUnavailable("Yahoo Finance returned no usable candles for the universe")
        return out

    def get_history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Candle]:
        if symbol not in self._instruments:
            raise MarketDataUnavailable(f"Unknown symbol: {symbol}")
        candles = self._candles.get(symbol)
        if not candles:
            raise MarketDataUnavailable(f"No Yahoo data for {symbol}")
        return [c for c in candles if (start is None or c.date >= start) and (end is None or c.date <= end)]

    def get_quote(self, symbol: str) -> Quote:
        candles = self.get_history(symbol, start=date.today() - timedelta(days=30))
        if not candles:
            raise MarketDataUnavailable(f"No recent Yahoo data for {symbol}")
        prev = candles[-2].close if len(candles) > 1 else None
        return Quote(symbol, candles[-1].close, prev, eod_timestamp(candles[-1].date), self.source, self.status)
