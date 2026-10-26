"""Paper-order execution. Every order runs in a single DB transaction that locks the
account row, so cash and holdings cannot drift apart under concurrent requests."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Account, Holding, Instrument, PaperOrder, Trade
from app.services.market import get_instrument, latest_price
from app.services.portfolio import OrderCalc, Position, TradingError, calculate_order


class OrderRejected(Exception):
    def __init__(self, error: TradingError, order: PaperOrder):
        super().__init__(error.message)
        self.error = error
        self.order = order


@dataclass(frozen=True)
class OrderPreview:
    instrument: Instrument
    price_date: date
    calc: OrderCalc


@dataclass(frozen=True)
class ExecutionResult:
    order: PaperOrder
    trade: Trade | None
    replayed: bool


def get_account(db: Session, for_update: bool = False) -> Account:
    stmt = select(Account).order_by(Account.id).limit(1)
    if for_update:
        stmt = stmt.with_for_update()
    account = db.scalar(stmt)
    if account is None:
        raise RuntimeError("No paper-trading account found; run the seed script")
    return account


def _position(holding: Holding | None) -> Position | None:
    return Position(holding.quantity, holding.cost_basis) if holding else None


def _find_by_key(db: Session, key: str) -> PaperOrder | None:
    return db.scalar(select(PaperOrder).where(PaperOrder.idempotency_key == key))


def preview_order(db: Session, settings: Settings, symbol: str, side: str, quantity: int) -> OrderPreview:
    """Price an order against the latest available close without writing anything."""
    instrument = get_instrument(db, symbol)
    lp = latest_price(db, instrument)
    account = get_account(db)
    holding = db.scalar(
        select(Holding).where(Holding.account_id == account.id, Holding.instrument_id == instrument.id)
    )
    calc = calculate_order(
        side, quantity, lp.price, account.cash, _position(holding), settings.paper_fee_percent, settings.paper_fee_flat
    )
    return OrderPreview(instrument, lp.price_date, calc)


def place_order(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    side: str,
    quantity: int,
    idempotency_key: str | None = None,
    fill: tuple[Decimal, date] | None = None,
    executed_at: datetime | None = None,
) -> ExecutionResult:
    """Execute a simulated order at the latest close (or at `fill` = (price, bar date) for seeding).

    Raises UnknownSymbol / PriceUnavailable (nothing recorded) or OrderRejected
    (a REJECTED order is recorded). Re-sending an idempotency key returns the
    original order instead of trading twice.
    """
    if idempotency_key and (existing := _find_by_key(db, idempotency_key)):
        return ExecutionResult(existing, existing.trade, replayed=True)

    instrument = get_instrument(db, symbol)
    if fill is None:
        lp = latest_price(db, instrument)
        fill = (lp.price, lp.price_date)
    price, price_date = fill

    account = get_account(db, for_update=True)
    account_id = account.id
    holding = db.scalar(
        select(Holding)
        .where(Holding.account_id == account_id, Holding.instrument_id == instrument.id)
        .with_for_update()
    )
    timestamps = {"created_at": executed_at} if executed_at else {}

    try:
        calc = calculate_order(
            side, quantity, price, account.cash, _position(holding), settings.paper_fee_percent, settings.paper_fee_flat
        )
    except TradingError as err:
        db.rollback()
        order = PaperOrder(
            account_id=account_id,
            instrument_id=instrument.id,
            side=side,
            quantity=quantity,
            status="REJECTED",
            reject_code=err.code,
            reject_reason=err.message,
            idempotency_key=idempotency_key,
            **timestamps,
        )
        db.add(order)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if idempotency_key and (existing := _find_by_key(db, idempotency_key)):
                return ExecutionResult(existing, existing.trade, replayed=True)
            raise
        raise OrderRejected(err, order) from err

    order = PaperOrder(
        account_id=account_id,
        instrument_id=instrument.id,
        side=side,
        quantity=quantity,
        status="EXECUTED",
        idempotency_key=idempotency_key,
        **timestamps,
    )
    trade = Trade(
        order=order,
        account_id=account_id,
        instrument_id=instrument.id,
        side=side,
        quantity=quantity,
        price=price,
        gross_amount=calc.gross_amount,
        fees=calc.fees,
        cash_change=calc.cash_change,
        realized_pnl=calc.realized_pnl,
        price_date=price_date,
        **({"executed_at": executed_at} if executed_at else {}),
    )
    db.add_all([order, trade])
    account.cash = calc.cash_after

    new_pos = calc.position_after
    if new_pos is None:
        if holding is not None:
            db.delete(holding)
    elif holding is None:
        db.add(
            Holding(
                account_id=account_id,
                instrument_id=instrument.id,
                quantity=new_pos.quantity,
                cost_basis=new_pos.cost_basis,
            )
        )
    else:
        holding.quantity, holding.cost_basis = new_pos.quantity, new_pos.cost_basis

    try:
        db.commit()
    except IntegrityError:
        # Concurrent request with the same idempotency key won the race.
        db.rollback()
        if idempotency_key and (existing := _find_by_key(db, idempotency_key)):
            return ExecutionResult(existing, existing.trade, replayed=True)
        raise
    return ExecutionResult(order, trade, replayed=False)
