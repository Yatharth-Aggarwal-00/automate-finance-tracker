from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.market.base import MarketDataProvider
from app.models import Instrument, PriceBar


def sync_market_data(db: Session, provider: MarketDataProvider) -> int:
    """Upsert instruments and daily candles from `provider`. Returns bars written."""
    written = 0
    now = datetime.now(UTC)
    for info in provider.list_instruments():
        inst = db.scalar(select(Instrument).where(Instrument.symbol == info.symbol))
        if inst is None:
            inst = Instrument(symbol=info.symbol)
            db.add(inst)
        inst.name, inst.exchange, inst.sector = info.name, info.exchange, info.sector
        inst.data_source, inst.data_status, inst.last_synced_at = provider.source, provider.status.value, now
        db.flush()

        rows = [
            {
                "instrument_id": inst.id,
                "date": c.date,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in provider.get_history(info.symbol)
        ]
        if rows:
            stmt = insert(PriceBar).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[PriceBar.instrument_id, PriceBar.date],
                set_={k: stmt.excluded[k] for k in ("open", "high", "low", "close", "volume")},
            )
            db.execute(stmt)
            written += len(rows)
    db.commit()
    return written
