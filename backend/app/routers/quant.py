from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.quant import engine
from app.quant.data import BENCHMARK_SYMBOL
from app.schemas import BacktestIn, BacktestOut, FactorOut, FactorsOut, PeriodOut, ScreenIn, ScreenOut

router = APIRouter(prefix="/api/quant", tags=["quant research"])
SCREEN_DISCLAIMER = (
    "Research ranking by the chosen factors on today's data. Check each factor's historical evidence "
    "before relying on it. Not a recommendation to buy or sell."
)


def _context(db: Session) -> engine.Context:
    ctx = engine.context(db)
    if ctx.panel.close.empty or len(ctx.dates) < 24:
        raise HTTPException(503, {"code": "NOT_ENOUGH_DATA", "message": "Need at least 2 years of prices for research"})
    return ctx


def _period(p: engine.PeriodMetrics) -> PeriodOut:
    return PeriodOut(**asdict(p))


@router.get("/factors", response_model=FactorsOut, summary="Factor library with historical evidence (IC, spreads)")
def get_factors(db: Session = Depends(get_db)):
    ctx = _context(db)
    catalog = engine.factor_catalog(ctx)
    reports = engine.factor_reports(ctx)
    return FactorsOut(
        universe_size=ctx.panel.close.shape[1],
        start=ctx.panel.close.index[0].date(),
        end=ctx.panel.close.index[-1].date(),
        rebalances=len(ctx.dates),
        test_start=ctx.test_start.date(),
        benchmark=BENCHMARK_SYMBOL if ctx.panel.benchmark is not None else None,
        data_source=ctx.panel.source,
        factors=[
            FactorOut(
                key=r.key,
                name=catalog[r.key].name,
                description=catalog[r.key].description,
                hypothesis=catalog[r.key].hypothesis,
                full=asdict(r.full),
                train=asdict(r.train),
                test=asdict(r.test),
                verdict=r.verdict,
            )
            for r in reports
        ],
        caveats=engine.CAVEATS,
    )


@router.post("/backtest", response_model=BacktestOut, summary="Monthly top-N backtest of a factor mix, with costs")
def post_backtest(body: BacktestIn, db: Session = Depends(get_db)):
    ctx = _context(db)
    try:
        rep = engine.run(ctx, body.weights, body.top_n, body.cost_bps)
    except ValueError as e:
        raise HTTPException(422, {"code": "BAD_FACTORS", "message": str(e)}) from e
    return BacktestOut(
        weights=rep.weights,
        top_n=rep.top_n,
        cost_per_side_pct=rep.cost_per_side_pct,
        risk_free_pct=engine.RF_ANNUAL * 100,
        test_start=rep.test_start.date(),
        full=_period(rep.full),
        train=_period(rep.train),
        test=_period(rep.test),
        curve=rep.curve,
        latest_holdings=rep.latest_holdings,
        latest_date=rep.latest_date.date() if rep.latest_date is not None else None,
        caveats=engine.CAVEATS,
    )


@router.post("/screen", response_model=ScreenOut, summary="Rank today's universe by a factor mix (research only)")
def post_screen(body: ScreenIn, db: Session = Depends(get_db)):
    ctx = _context(db)
    try:
        as_of, rows = engine.screen(ctx, body.weights)
    except ValueError as e:
        raise HTTPException(422, {"code": "BAD_FACTORS", "message": str(e)}) from e
    return ScreenOut(
        as_of=as_of.date(),
        weights=body.weights,
        rows=[asdict(r) for r in rows],
        disclaimer=SCREEN_DISCLAIMER,
    )
