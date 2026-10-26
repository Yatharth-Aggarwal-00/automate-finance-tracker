from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings, get_settings
from app.db import get_db
from app.models import PaperOrder
from app.routers.portfolio import trade_out
from app.schemas import ErrorResponse, OrderIn, OrderOut, OrderPreviewOut, OrderResultOut
from app.services.trading import get_account, place_order, preview_order

router = APIRouter(prefix="/api/paper-trades", tags=["paper trading"])
ERRORS = {
    400: {"model": ErrorResponse, "description": "Rejected: insufficient cash or holdings"},
    404: {"model": ErrorResponse, "description": "Unknown symbol"},
    503: {"model": ErrorResponse, "description": "No price available"},
}


def order_out(o: PaperOrder) -> OrderOut:
    return OrderOut(
        id=o.id,
        symbol=o.instrument.symbol,
        side=o.side,
        quantity=o.quantity,
        status=o.status,
        reject_code=o.reject_code,
        reject_reason=o.reject_reason,
        created_at=o.created_at,
        trade=trade_out(o.trade) if o.trade else None,
    )


@router.post("/preview", response_model=OrderPreviewOut, responses=ERRORS, summary="Price a simulated order without executing it")
def preview(body: OrderIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    p = preview_order(db, settings, body.symbol, body.side, body.quantity)
    c = p.calc
    return OrderPreviewOut(
        symbol=p.instrument.symbol,
        side=c.side,
        quantity=c.quantity,
        price=c.price,
        price_date=p.price_date,
        gross_amount=c.gross_amount,
        fees=c.fees,
        cash_change=c.cash_change,
        cash_after=c.cash_after,
        position_quantity_after=c.position_after.quantity if c.position_after else 0,
        realized_pnl=c.realized_pnl,
        fee_note=f"Estimated charges: {settings.paper_fee_percent}% of order value + ₹{settings.paper_fee_flat} (simulated)",
    )


@router.post(
    "",
    response_model=OrderResultOut,
    status_code=201,
    responses=ERRORS,
    summary="Execute a simulated (paper) order at the latest available close",
)
def create_paper_trade(
    body: OrderIn,
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        description="Unique per order attempt; resending the same key returns the original result",
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = place_order(
        db, settings, symbol=body.symbol, side=body.side, quantity=body.quantity, idempotency_key=idempotency_key
    )
    db.refresh(result.order)
    return OrderResultOut(replayed=result.replayed, order=order_out(result.order), cash=get_account(db).cash)


@router.get("", response_model=list[OrderOut], summary="All paper orders, including rejected ones")
def list_orders(limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    orders = db.scalars(
        select(PaperOrder)
        .options(joinedload(PaperOrder.instrument), joinedload(PaperOrder.trade))
        .order_by(PaperOrder.created_at.desc(), PaperOrder.id.desc())
        .limit(limit)
    )
    return [order_out(o) for o in orders]
