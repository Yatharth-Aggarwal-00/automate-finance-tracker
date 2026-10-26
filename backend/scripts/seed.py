"""Load market data and create the demo paper account. Safe to run repeatedly.

    python -m scripts.seed           # sync prices; create account + demo trades if none exists
    python -m scripts.seed --reset   # wipe paper account, orders and trades, then re-seed
"""

import argparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.market import get_provider
from app.market.csv_provider import eod_timestamp
from app.market.sync import sync_market_data
from app.models import Account, Holding, Instrument, PaperOrder, PriceBar, Trade
from app.services.trading import place_order

# (trading days after the account opens, symbol, side, quantity)
DEMO_TRADES = [
    (1, "TCS", "BUY", 8),
    (1, "INFY", "BUY", 15),
    (6, "RELIANCE", "BUY", 10),
    (41, "HDFCBANK", "BUY", 12),
    (81, "INFY", "SELL", 5),
]
ACCOUNT_OPENS_DAYS_AGO = 120


def reset_account(db: Session) -> None:
    for model in (Trade, PaperOrder, Holding, Account):
        db.execute(delete(model))
    db.commit()


def seed(db: Session, settings: Settings, demo_trades: bool = True) -> str:
    bars = sync_market_data(db, get_provider(settings))
    if db.scalar(select(Account)) is not None:
        return f"Synced {bars} price bars; account already exists"

    dates = list(db.scalars(select(PriceBar.date).distinct().order_by(PriceBar.date)))
    if not dates:
        raise SystemExit("No price data loaded; check MARKET_DATA_DIR")
    start = max(0, len(dates) - ACCOUNT_OPENS_DAYS_AGO)
    db.add(
        Account(
            name="Demo paper account",
            initial_cash=settings.initial_cash,
            cash=settings.initial_cash,
            created_at=eod_timestamp(dates[start]),
        )
    )
    db.commit()
    if not demo_trades:
        return f"Synced {bars} price bars; created empty account"

    for i, (offset, symbol, side, qty) in enumerate(DEMO_TRADES):
        d = dates[min(start + offset, len(dates) - 1)]
        close = db.scalar(
            select(PriceBar.close).join(Instrument).where(Instrument.symbol == symbol, PriceBar.date == d)
        )
        place_order(
            db,
            settings,
            symbol=symbol,
            side=side,
            quantity=qty,
            idempotency_key=f"seed-demo-{i}",
            fill=(close, d),
            executed_at=eod_timestamp(d),
        )
    return f"Synced {bars} price bars; created account with {len(DEMO_TRADES)} demo trades"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="delete the paper account and all orders/trades first")
    p.add_argument("--empty", action="store_true", help="create the account without demo trades")
    args = p.parse_args()
    with SessionLocal() as session:
        if args.reset:
            reset_account(session)
        print(seed(session, get_settings(), demo_trades=not args.empty))
