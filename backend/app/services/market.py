from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.market.csv_provider import eod_timestamp
from app.models import Instrument, PriceBar
from app.services import indicators
from app.services.portfolio import TradingError


class UnknownSymbol(TradingError):
    code = "UNKNOWN_SYMBOL"


class PriceUnavailable(TradingError):
    code = "PRICE_UNAVAILABLE"


@dataclass(frozen=True)
class LatestPrice:
    instrument: Instrument
    price: Decimal
    price_date: date
    previous_close: Decimal | None

    @property
    def as_of(self) -> datetime:
        return eod_timestamp(self.price_date)

    @property
    def change(self) -> Decimal | None:
        return None if self.previous_close is None else self.price - self.previous_close

    @property
    def change_pct(self) -> float | None:
        if not self.previous_close:
            return None
        return round(float((self.price - self.previous_close) / self.previous_close * 100), 2)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def get_instrument(db: Session, symbol: str) -> Instrument:
    inst = db.scalar(select(Instrument).where(Instrument.symbol == normalize_symbol(symbol)))
    if inst is None:
        raise UnknownSymbol(f"Unknown symbol: {symbol}")
    return inst


def latest_prices(db: Session, instrument_ids: list[int] | None = None) -> dict[int, LatestPrice]:
    """Latest close and previous close per instrument, from stored EOD bars."""
    rn = func.row_number().over(partition_by=PriceBar.instrument_id, order_by=PriceBar.date.desc()).label("rn")
    inner = select(PriceBar.instrument_id, PriceBar.date, PriceBar.close, rn)
    if instrument_ids is not None:
        inner = inner.where(PriceBar.instrument_id.in_(instrument_ids))
    sub = inner.subquery()
    rows = db.execute(select(sub).where(sub.c.rn <= 2).order_by(sub.c.instrument_id, sub.c.rn)).all()

    by_id: dict[int, list] = {}
    for r in rows:
        by_id.setdefault(r.instrument_id, []).append(r)
    instruments = {i.id: i for i in db.scalars(select(Instrument).where(Instrument.id.in_(by_id.keys())))}
    return {
        iid: LatestPrice(instruments[iid], bars[0].close, bars[0].date, bars[1].close if len(bars) > 1 else None)
        for iid, bars in by_id.items()
    }


def latest_price(db: Session, instrument: Instrument) -> LatestPrice:
    lp = latest_prices(db, [instrument.id]).get(instrument.id)
    if lp is None:
        raise PriceUnavailable(f"No price data available for {instrument.symbol}")
    return lp


def price_history(db: Session, instrument_id: int) -> list[PriceBar]:
    return list(db.scalars(select(PriceBar).where(PriceBar.instrument_id == instrument_id).order_by(PriceBar.date)))


@dataclass(frozen=True)
class IndicatorSnapshot:
    sma20: float | None
    sma50: float | None
    rsi14: float | None
    volatility_20d: float | None  # annualised %


def round2(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def indicator_snapshot(closes: list[float]) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        sma20=round2(indicators.latest(indicators.sma(closes, 20))),
        sma50=round2(indicators.latest(indicators.sma(closes, 50))),
        rsi14=round2(indicators.latest(indicators.rsi(closes, 14))),
        volatility_20d=round2(indicators.historical_volatility(closes, 20)),
    )
