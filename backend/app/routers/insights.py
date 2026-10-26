from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import InsightsOut
from app.services.insights import DISCLAIMER, build_metrics, insight_dicts, llm_summary, rule_based_insights
from app.services.market import indicator_snapshot, price_history
from app.services.reports import build_report

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("", response_model=InsightsOut, summary="Plain-English explanations of portfolio metrics")
def get_insights(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    report = build_report(db)
    snapshots = {
        sym: indicator_snapshot([float(b.close) for b in price_history(db, inst.id)])
        for sym, inst in report.instruments.items()
    }
    metrics = build_metrics(report, snapshots)
    insights = rule_based_insights(metrics)

    summary = error = None
    if settings.llm_enabled:
        summary, error = llm_summary(metrics, insights, settings)

    return InsightsOut(
        generated_by="rules+llm" if summary else "rules",
        model=settings.anthropic_model if summary else None,
        summary=summary,
        llm_error=error,
        disclaimer=DISCLAIMER,
        insights=insight_dicts(insights),
        metrics=metrics,
        data_status=report.data_status,
        as_of=report.as_of,
    )
