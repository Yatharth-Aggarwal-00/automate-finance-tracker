"""Load market data and create the demo paper account. Safe to run repeatedly.

    python -m scripts.seed           # sync prices; create account + demo trades if none exists
    python -m scripts.seed --reset   # wipe paper account, orders and trades, then re-seed

If the configured provider (e.g. Yahoo) is unreachable, existing prices are kept;
with an empty database the bundled SIMULATED fixtures are loaded instead, so the
app always starts.
"""

import argparse
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.market import fallback_provider, get_provider
from app.market.base import MarketDataUnavailable
from app.market.csv_provider import eod_timestamp
from app.market.sync import sync_market_data
from app.models import Account, Holding, Instrument, PaperOrder, PriceBar, Trade
from app.services.trading import OrderRejected, place_order

# (calendar days before the latest price, symbol, side, quantity). Chosen so the tax features
# have something to show: lots older than 12 months, one ~11 months old that turns long-term
# soon, and a long-term sale earlier in the current financial year.
DEMO_TRADES = [
    (420, "TCS", "BUY", 6),
    (420, "INFY", "BUY", 12),
    (345, "HDFCBANK", "BUY", 20),
    (200, "RELIANCE", "BUY", 8),
    (90, "INFY", "SELL", 4),
    (30, "ICICIBANK", "BUY", 5),
]
ACCOUNT_OPENS_DAYS_AGO = 430


def reset_account(db: Session) -> None:
    for model in (Trade, PaperOrder, Holding, Account):
        db.execute(delete(model))
    db.commit()


def load_market_data(db: Session, settings: Settings) -> str:
    sources_before = set(db.scalars(select(Instrument.data_source).distinct()))
    try:
        provider = get_provider(settings)
        msg = f"Synced {sync_market_data(db, provider)} price bars from {provider.source}"
    except MarketDataUnavailable as e:
        db.rollback()
        if db.scalar(select(PriceBar.date).limit(1)) is not None:
            return f"WARNING: {e}. Keeping the existing price data."
        provider = fallback_provider(settings)
        msg = f"WARNING: {e}. Loaded {sync_market_data(db, provider)} bars of bundled SIMULATED data instead"
    if sources_before and sources_before != {provider.source} and db.scalar(select(Trade.id).limit(1)):
        msg += (
            f"\nWARNING: existing paper trades were priced on {', '.join(sorted(sources_before))} data, "
            f"now {provider.source}. Run `python -m scripts.seed --reset` for a consistent portfolio."
        )
    return msg


def seed(db: Session, settings: Settings, demo_trades: bool = True) -> str:
    synced = load_market_data(db, settings)
    if db.scalar(select(Account)) is not None:
        return f"{synced}; account already exists"

    dates = list(db.scalars(select(PriceBar.date).distinct().order_by(PriceBar.date)))
    if not dates:
        raise SystemExit("No price data loaded; check MARKET_DATA_PROVIDER / MARKET_DATA_DIR")
    latest = dates[-1]

    def day(days_ago: int):
        return max(latest - timedelta(days=days_ago), dates[0])

    db.add(
        Account(
            name="Demo paper account",
            initial_cash=settings.initial_cash,
            cash=settings.initial_cash,
            created_at=eod_timestamp(day(ACCOUNT_OPENS_DAYS_AGO)),
        )
    )
    db.commit()
    if not demo_trades:
        return f"{synced}; created empty account"

    placed = 0
    for i, (days_ago, symbol, side, qty) in enumerate(DEMO_TRADES):
        d = day(days_ago)
        bar = db.execute(
            select(PriceBar.close, PriceBar.date)
            .join(Instrument)
            .where(Instrument.symbol == symbol, PriceBar.date <= d)
            .order_by(PriceBar.date.desc())
            .limit(1)
        ).first()
        if bar is None:
            continue  # symbol not in this provider's universe
        try:
            place_order(
                db,
                settings,
                symbol=symbol,
                side=side,
                quantity=qty,
                idempotency_key=f"seed-demo-{i}",
                fill=(bar.close, bar.date),
                executed_at=eod_timestamp(bar.date),
            )
            placed += 1
        except OrderRejected:
            continue  # e.g. prices made the demo too expensive for the starting cash
    return f"{synced}; created account with {placed} demo trades"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="delete the paper account and all orders/trades first")
    p.add_argument("--empty", action="store_true", help="create the account without demo trades")
    args = p.parse_args()
    with SessionLocal() as session:
        if args.reset:
            reset_account(session)
        print(seed(session, get_settings(), demo_trades=not args.empty))
