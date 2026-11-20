from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import (
    BuyCheckOut,
    CheckIn,
    ErrorResponse,
    OpenLotOut,
    RealizedPieceOut,
    SellCheckOut,
    SellOptionOut,
    TaxEstimateOut,
    TaxRatesOut,
    TaxSummaryOut,
)
from app.services import tax
from app.services.checks import buy_check, sell_check, tax_summary
from app.services.tax import RealizedGain, TaxEstimate, long_term_from

router = APIRouter(tags=["decision checks"])
ERRORS = {
    400: {"model": ErrorResponse, "description": "Insufficient cash or holdings"},
    404: {"model": ErrorResponse, "description": "Unknown symbol"},
}
TAX_DISCLAIMER = (
    "Estimate under FY 2026-27 rules for listed shares: 20% short-term, 12.5% long-term above "
    "₹1.25 lakh/year, plus 4% cess. Ignores surcharge, carried-forward losses and other income. "
    "Not tax advice."
)
CHECK_DISCLAIMER = "Historical facts only. Past falls do not predict future prices; this is not a recommendation."


def piece_out(g: RealizedGain) -> RealizedPieceOut:
    return RealizedPieceOut(
        symbol=g.symbol,
        buy_date=g.buy_date,
        sell_date=g.sell_date,
        quantity=g.quantity,
        cost=g.cost,
        proceeds=g.proceeds,
        gain=g.gain,
        long_term=g.long_term,
        long_term_from=long_term_from(g.buy_date),
    )


def estimate_out(e: TaxEstimate) -> TaxEstimateOut:
    return TaxEstimateOut(**e.__dict__)


@router.post("/api/checks/sell", response_model=SellCheckOut, responses=ERRORS,
             summary="Tax impact of a sale (FIFO lots), with cheaper timing options")
def check_sell(body: CheckIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    c = sell_check(db, settings, body.symbol, body.quantity)
    return SellCheckOut(
        symbol=c.symbol,
        quantity=c.quantity,
        price=c.price,
        proceeds=c.proceeds,
        sell_date=c.sell_date,
        fy=c.fy,
        pieces=[piece_out(p) for p in c.pieces],
        gain=c.gain,
        tax=c.tax,
        fy_before=estimate_out(c.fy_before),
        fy_after=estimate_out(c.fy_after),
        options=[SellOptionOut(**o.__dict__) for o in c.options],
        notes=c.notes,
        disclaimer=TAX_DISCLAIMER,
    )


@router.post("/api/checks/buy", response_model=BuyCheckOut, responses=ERRORS,
             summary="Historical risk, concentration and activity facts before a buy")
def check_buy(body: CheckIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    c = buy_check(db, settings, body.symbol, body.quantity)
    return BuyCheckOut(
        symbol=c.symbol,
        quantity=c.quantity,
        amount=c.amount,
        history_years=c.history_years,
        max_drawdown_pct=c.drawdown.pct if c.drawdown else None,
        max_drawdown_peak=c.drawdown.peak_date if c.drawdown else None,
        max_drawdown_trough=c.drawdown.trough_date if c.drawdown else None,
        max_drawdown_rupees=c.drawdown_rupees,
        worst_month_pct=c.worst_month.pct if c.worst_month else None,
        worst_month_start=c.worst_month.start_date if c.worst_month else None,
        worst_month_rupees=c.worst_month_rupees,
        losing_year_pct=c.losing_year_pct,
        volatility_1y=c.volatility_1y,
        position_pct_after=c.position_pct_after,
        sector=c.sector,
        sector_pct_after=c.sector_pct_after,
        trades_30d=c.trades_30d,
        charges_fy=c.charges_fy,
        flags=[{"kind": f.kind, "level": f.level, "text": f.text} for f in c.flags],
        disclaimer=CHECK_DISCLAIMER,
    )


@router.get("/api/tax/summary", response_model=TaxSummaryOut,
            summary="This financial year's realized gains, estimated tax, lots and timing opportunities")
def get_tax_summary(db: Session = Depends(get_db)):
    s = tax_summary(db)
    return TaxSummaryOut(
        fy=s.fy,
        fy_end=s.fy_end,
        days_left_in_fy=s.days_left_in_fy,
        realized=[piece_out(g) for g in s.realized],
        estimate=estimate_out(s.estimate),
        lots=[
            OpenLotOut(
                symbol=l.lot.symbol,
                buy_date=l.lot.buy_date,
                quantity=l.lot.quantity,
                cost=l.lot.cost,
                price=l.price,
                market_value=l.market_value,
                unrealized_gain=l.unrealized_gain,
                long_term_from=l.long_term_from,
                days_to_long_term=l.days_to_long_term,
                extra_tax_if_sold_today=l.extra_tax_if_sold_today,
            )
            for l in s.lots
        ],
        harvestable_ltcg=s.harvestable_ltcg,
        unrealized_long_term_gain=s.unrealized_long_term_gain,
        rates=TaxRatesOut(
            stcg_pct=float(tax.STCG_RATE * 100),
            ltcg_pct=float(tax.LTCG_RATE * 100),
            ltcg_exemption=tax.LTCG_EXEMPTION,
            cess_pct=float(tax.CESS * 100),
        ),
        disclaimer=TAX_DISCLAIMER,
    )
