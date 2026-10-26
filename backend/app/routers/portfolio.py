from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Trade
from app.schemas import HoldingOut, PortfolioOut, PortfolioPointOut, TradeOut
from app.services.reports import build_history, build_report

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def trade_out(t: Trade) -> TradeOut:
    return TradeOut(
        id=t.id,
        order_id=t.order_id,
        symbol=t.instrument.symbol,
        side=t.side,
        quantity=t.quantity,
        price=t.price,
        gross_amount=t.gross_amount,
        fees=t.fees,
        cash_change=t.cash_change,
        realized_pnl=t.realized_pnl,
        price_date=t.price_date,
        executed_at=t.executed_at,
    )


@router.get("", response_model=PortfolioOut, summary="Portfolio summary and holdings (paper trading)")
def get_portfolio(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    r = build_report(db)
    s = r.summary
    holdings = [
        HoldingOut(
            symbol=h.symbol,
            name=r.instruments[h.symbol].name,
            sector=r.instruments[h.symbol].sector,
            quantity=h.quantity,
            avg_cost=h.avg_cost,
            cost_basis=h.cost_basis,
            price=h.price,
            market_value=h.market_value,
            unrealized_pnl=h.unrealized_pnl,
            unrealized_pnl_pct=h.unrealized_pnl_pct,
            weight_pct=round(float(h.market_value / s.total_value * 100), 2) if s.total_value else 0.0,
            price_as_of=r.prices[h.symbol].as_of if h.symbol in r.prices else None,
        )
        for h in s.holdings
    ]
    return PortfolioOut(
        initial_cash=s.initial_cash,
        cash=s.cash,
        invested=s.invested,
        market_value=s.market_value,
        total_value=s.total_value,
        unrealized_pnl=s.unrealized_pnl,
        realized_pnl=s.realized_pnl,
        total_pnl=s.total_pnl,
        return_pct=s.return_pct,
        holdings=holdings,
        data_status=r.data_status,
        as_of=r.as_of,
        fee_percent=settings.paper_fee_percent,
        fee_flat=settings.paper_fee_flat,
    )


@router.get("/history", response_model=list[PortfolioPointOut], summary="Daily portfolio value rebuilt from the trade ledger")
def get_portfolio_history(db: Session = Depends(get_db)):
    return [PortfolioPointOut(**p.__dict__) for p in build_history(db)]


@router.get("/transactions", response_model=list[TradeOut], summary="Executed paper trades, newest first")
def get_transactions(limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    trades = db.scalars(
        select(Trade).options(joinedload(Trade.instrument)).order_by(Trade.executed_at.desc(), Trade.id.desc()).limit(limit)
    )
    return [trade_out(t) for t in trades]
