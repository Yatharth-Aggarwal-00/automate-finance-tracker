from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.market.csv_provider import eod_timestamp
from app.models import Instrument
from app.schemas import CandleOut, ErrorResponse, HistoryOut, IndicatorsOut, QuoteOut, StockOut
from app.services import indicators
from app.services.market import (
    LatestPrice,
    get_instrument,
    indicator_snapshot,
    latest_prices,
    price_history,
    round2,
)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Unknown symbol"}}


def _stock_out(inst: Instrument, lp: LatestPrice | None) -> dict:
    return {
        "symbol": inst.symbol,
        "name": inst.name,
        "exchange": inst.exchange,
        "sector": inst.sector,
        "price": lp.price if lp else None,
        "previous_close": lp.previous_close if lp else None,
        "change": lp.change if lp else None,
        "change_pct": lp.change_pct if lp else None,
        "as_of": lp.as_of if lp else None,
        "data_status": inst.data_status,
        "data_source": inst.data_source,
    }


@router.get("", response_model=list[StockOut], summary="List or search supported instruments")
def list_stocks(q: str | None = Query(None, max_length=64, description="Filter by symbol or name"), db: Session = Depends(get_db)):
    stmt = select(Instrument).order_by(Instrument.symbol)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Instrument.symbol.ilike(like), Instrument.name.ilike(like)))
    instruments = list(db.scalars(stmt))
    prices = latest_prices(db, [i.id for i in instruments])
    return [_stock_out(i, prices.get(i.id)) for i in instruments]


@router.get("/{symbol}/quote", response_model=QuoteOut, responses=NOT_FOUND, summary="Latest available quote and indicators")
def get_quote(symbol: str, db: Session = Depends(get_db)):
    inst = get_instrument(db, symbol)
    bars = price_history(db, inst.id)
    lp = latest_prices(db, [inst.id]).get(inst.id)
    snap = indicator_snapshot([float(b.close) for b in bars])
    return {
        **_stock_out(inst, lp),
        "indicators": IndicatorsOut(**snap.__dict__),
        "history_points": len(bars),
    }


@router.get("/{symbol}/history", response_model=HistoryOut, responses=NOT_FOUND, summary="Daily OHLCV candles with SMA/RSI")
def get_history(
    symbol: str,
    days: int = Query(180, ge=5, le=2000, description="Number of most recent trading days to return"),
    db: Session = Depends(get_db),
):
    inst = get_instrument(db, symbol)
    bars = price_history(db, inst.id)
    closes = [float(b.close) for b in bars]
    # Indicators are computed on the full series, then sliced, so early points are accurate.
    sma20, sma50, rsi14 = indicators.sma(closes, 20), indicators.sma(closes, 50), indicators.rsi(closes, 14)
    start = max(0, len(bars) - days)
    candles = [
        CandleOut(
            date=b.date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            sma20=round2(sma20[i]),
            sma50=round2(sma50[i]),
            rsi14=round2(rsi14[i]),
        )
        for i, b in enumerate(bars)
        if i >= start
    ]
    return HistoryOut(
        symbol=inst.symbol,
        data_status=inst.data_status,
        data_source=inst.data_source,
        as_of=eod_timestamp(bars[-1].date) if bars else None,
        candles=candles,
    )
