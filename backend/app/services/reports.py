"""Read-side assembly of portfolio data from the database."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.market.base import least_live
from app.models import Account, Holding, Instrument, PriceBar, Trade
from app.services.market import LatestPrice, latest_prices
from app.services.portfolio import (
    ZERO,
    LedgerEntry,
    PortfolioSummary,
    Position,
    ValuePoint,
    portfolio_history,
    summarize,
)
from app.services.trading import get_account


@dataclass(frozen=True)
class PortfolioReport:
    account: Account
    summary: PortfolioSummary
    instruments: dict[str, Instrument]
    prices: dict[str, LatestPrice]
    data_status: str
    as_of: datetime | None


def build_report(db: Session) -> PortfolioReport:
    account = get_account(db)
    holdings = list(
        db.scalars(
            select(Holding)
            .options(joinedload(Holding.instrument))
            .where(Holding.account_id == account.id)
            .order_by(Holding.id)
        )
    )
    lp = latest_prices(db, [h.instrument_id for h in holdings])
    realized = db.scalar(
        select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(Trade.account_id == account.id)
    )
    positions = []
    for h in holdings:
        # Fall back to average cost if a holding somehow has no price bar.
        price = lp[h.instrument_id].price if h.instrument_id in lp else Position(h.quantity, h.cost_basis).avg_cost
        positions.append((h.instrument.symbol, Position(h.quantity, h.cost_basis), price))
    summary = summarize(account.initial_cash, account.cash, positions, realized or ZERO)
    instruments = {h.instrument.symbol: h.instrument for h in holdings}
    prices = {lp[h.instrument_id].instrument.symbol: lp[h.instrument_id] for h in holdings if h.instrument_id in lp}
    statuses = {i.data_status for i in instruments.values()} or set(db.scalars(select(Instrument.data_status)))
    return PortfolioReport(
        account=account,
        summary=summary,
        instruments=instruments,
        prices=prices,
        data_status=least_live(statuses),
        as_of=max((p.as_of for p in prices.values()), default=None),
    )


def build_history(db: Session) -> list[ValuePoint]:
    account = get_account(db)
    trades = list(
        db.scalars(select(Trade).options(joinedload(Trade.instrument)).where(Trade.account_id == account.id))
    )
    start: date = min([account.created_at.date()] + [t.price_date for t in trades])
    symbols = {t.instrument_id: t.instrument.symbol for t in trades}

    dates = list(db.scalars(select(PriceBar.date).distinct().where(PriceBar.date >= start).order_by(PriceBar.date)))
    closes: dict[str, dict[date, object]] = {s: {} for s in symbols.values()}
    if symbols:
        for iid, d, close in db.execute(
            select(PriceBar.instrument_id, PriceBar.date, PriceBar.close).where(
                PriceBar.instrument_id.in_(symbols.keys())
            )
        ):
            closes[symbols[iid]][d] = close
    ledger = [LedgerEntry(t.price_date, t.instrument.symbol, t.side, t.quantity, t.cash_change) for t in trades]
    return portfolio_history(account.initial_cash, ledger, closes, dates)
