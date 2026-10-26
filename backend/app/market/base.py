"""Market-data provider interface.

The app never talks to a provider from request handlers. Providers are used by
`app.market.sync` to load instruments and daily candles into Postgres, and the API
reads from the database. Swapping providers = change MARKET_DATA_PROVIDER and re-sync.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class DataStatus(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    HISTORICAL = "HISTORICAL"
    SIMULATED = "SIMULATED"


STATUS_ORDER = [DataStatus.SIMULATED, DataStatus.HISTORICAL, DataStatus.DELAYED, DataStatus.LIVE]


def least_live(statuses) -> str:
    """When sources are mixed, report the weakest label (e.g. any SIMULATED -> SIMULATED)."""
    return DataStatus(min(statuses, default=DataStatus.SIMULATED, key=lambda s: STATUS_ORDER.index(DataStatus(s)))).value


class MarketDataUnavailable(Exception):
    pass


@dataclass(frozen=True)
class InstrumentInfo:
    symbol: str
    name: str
    exchange: str
    sector: str


@dataclass(frozen=True)
class Candle:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal
    previous_close: Decimal | None
    as_of: datetime
    source: str
    status: DataStatus


class MarketDataProvider(Protocol):
    source: str
    status: DataStatus

    def list_instruments(self, query: str | None = None) -> list[InstrumentInfo]: ...

    def get_quote(self, symbol: str) -> Quote: ...

    def get_history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Candle]: ...
