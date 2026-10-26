"""Plain-English explanations of computed metrics.

Rule-based insights are always produced and are deterministic. When an Anthropic
API key is configured, Claude additionally writes a short summary *of the same
metrics*; it is instructed not to add prices, news, events or predictions.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from decimal import Decimal

import anthropic

from app.config import Settings
from app.services.market import IndicatorSnapshot
from app.services.portfolio import inr
from app.services.reports import PortfolioReport

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Informational only. Generated from simulated data and calculated metrics; "
    "not a prediction, recommendation or personalised financial advice."
)

SECTOR_CONCENTRATION_PCT = 40
SINGLE_STOCK_PCT = 30
HIGH_CASH_PCT = 50
LOW_CASH_PCT = 5
RSI_HIGH, RSI_LOW = 70, 30
TREND_GAP_PCT = 5
HIGH_VOLATILITY_PCT = 35

# Models that accept the server-side refusal fallback parameter.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


@dataclass(frozen=True)
class Insight:
    kind: str
    severity: str  # info | attention
    title: str
    text: str
    symbols: list[str] = field(default_factory=list)


def _r(x: float | Decimal | None, nd: int = 1) -> float | None:
    return None if x is None else round(float(x), nd)


def build_metrics(report: PortfolioReport, snapshots: dict[str, IndicatorSnapshot]) -> dict:
    s = report.summary
    total = s.total_value
    sectors: dict[str, Decimal] = {}
    holdings = []
    for h in s.holdings:
        sector = report.instruments[h.symbol].sector
        sectors[sector] = sectors.get(sector, Decimal(0)) + h.market_value
        snap = snapshots.get(h.symbol)
        holdings.append(
            {
                "symbol": h.symbol,
                "sector": sector,
                "quantity": h.quantity,
                "price": float(h.price),
                "market_value": float(h.market_value),
                "weight_pct_of_portfolio": _r(h.market_value / total * 100) if total else 0.0,
                "unrealized_pnl": float(h.unrealized_pnl),
                "unrealized_pnl_pct": float(h.unrealized_pnl_pct),
                "sma20": _r(snap.sma20, 2) if snap else None,
                "sma50": _r(snap.sma50, 2) if snap else None,
                "rsi14": _r(snap.rsi14) if snap else None,
                "volatility_20d_annualised_pct": _r(snap.volatility_20d) if snap else None,
            }
        )
    mv = s.market_value
    sector_rows = sorted(
        (
            {
                "sector": k,
                "market_value": float(v),
                "weight_pct_of_holdings": _r(v / mv * 100) if mv else 0.0,
                "weight_pct_of_portfolio": _r(v / total * 100) if total else 0.0,
            }
            for k, v in sectors.items()
        ),
        key=lambda r: -r["market_value"],
    )
    return {
        "initial_cash": float(s.initial_cash),
        "total_value": float(total),
        "cash": float(s.cash),
        "cash_pct_of_portfolio": _r(s.cash / total * 100) if total else 0.0,
        "invested_cost_basis": float(s.invested),
        "holdings_market_value": float(mv),
        "unrealized_pnl": float(s.unrealized_pnl),
        "realized_pnl": float(s.realized_pnl),
        "total_pnl": float(s.total_pnl),
        "return_pct": float(s.return_pct),
        "holding_count": len(holdings),
        "sectors": sector_rows,
        "holdings": holdings,
    }


def rule_based_insights(m: dict) -> list[Insight]:
    out: list[Insight] = []
    direction = "up" if m["total_pnl"] >= 0 else "down"
    out.append(
        Insight(
            "performance",
            "info",
            "Overall performance",
            f"Your paper portfolio is {direction} {inr(abs(Decimal(str(m['total_pnl']))))} "
            f"({m['return_pct']:+.2f}%) against the {inr(Decimal(str(m['initial_cash'])))} starting cash: "
            f"{inr(Decimal(str(m['realized_pnl'])))} realized and {inr(Decimal(str(m['unrealized_pnl'])))} unrealized.",
        )
    )

    if m["holding_count"] == 0:
        out.append(
            Insight(
                "cash",
                "info",
                "All cash",
                "Your portfolio is entirely virtual cash, so market moves do not change its value yet.",
            )
        )
        return out

    top = m["sectors"][0]
    if len(m["sectors"]) == 1 or top["weight_pct_of_holdings"] >= SECTOR_CONCENTRATION_PCT:
        out.append(
            Insight(
                "sector_concentration",
                "attention",
                f"Concentrated in {top['sector']}",
                f"Your portfolio is concentrated in the {top['sector']} sector "
                f"({top['weight_pct_of_holdings']:.1f}% of your holdings by market value). "
                f"A decline across {top['sector']} stocks could have a larger effect on your overall portfolio.",
            )
        )

    for h in m["holdings"]:
        if h["weight_pct_of_portfolio"] >= SINGLE_STOCK_PCT:
            out.append(
                Insight(
                    "single_stock",
                    "attention",
                    f"Large position in {h['symbol']}",
                    f"{h['symbol']} is {h['weight_pct_of_portfolio']:.1f}% of your total portfolio value, "
                    f"so a move in this one stock has an outsized effect on the whole portfolio.",
                    [h["symbol"]],
                )
            )

    cash_pct = m["cash_pct_of_portfolio"]
    if cash_pct >= HIGH_CASH_PCT:
        out.append(
            Insight(
                "cash",
                "info",
                "High cash share",
                f"{cash_pct:.1f}% of your portfolio is uninvested virtual cash, "
                "so market moves affect only part of its value.",
            )
        )
    elif cash_pct < LOW_CASH_PCT:
        out.append(
            Insight(
                "cash",
                "info",
                "Little cash left",
                f"Only {cash_pct:.1f}% of your portfolio is cash, which limits further paper buys.",
            )
        )

    for h in m["holdings"]:
        sym, rsi = h["symbol"], h["rsi14"]
        if rsi is not None and rsi >= RSI_HIGH:
            out.append(
                Insight(
                    "rsi",
                    "info",
                    f"{sym} RSI is high",
                    f"{sym}'s 14-day RSI is {rsi:.0f}, above {RSI_HIGH}. Traders often call this 'overbought', "
                    "meaning recent gains were strong; it does not reliably indicate the price will fall.",
                    [sym],
                )
            )
        elif rsi is not None and rsi <= RSI_LOW:
            out.append(
                Insight(
                    "rsi",
                    "info",
                    f"{sym} RSI is low",
                    f"{sym}'s 14-day RSI is {rsi:.0f}, below {RSI_LOW}. Traders often call this 'oversold', "
                    "meaning recent losses were strong; it does not reliably indicate the price will rise.",
                    [sym],
                )
            )
        if h["sma50"]:
            gap = (h["price"] - h["sma50"]) / h["sma50"] * 100
            if abs(gap) >= TREND_GAP_PCT:
                where = "above" if gap > 0 else "below"
                out.append(
                    Insight(
                        "trend",
                        "info",
                        f"{sym} vs its 50-day average",
                        f"{sym} is trading {abs(gap):.1f}% {where} its 50-day simple moving average "
                        f"(₹{h['sma50']:,.2f}), a sign of a recent {'up' if gap > 0 else 'down'}ward trend.",
                        [sym],
                    )
                )
        vol = h["volatility_20d_annualised_pct"]
        if vol is not None and vol >= HIGH_VOLATILITY_PCT:
            out.append(
                Insight(
                    "volatility",
                    "attention",
                    f"{sym} is volatile",
                    f"{sym}'s 20-day historical volatility is {vol:.0f}% (annualised), meaning its price "
                    "has been swinging more than usual day to day.",
                    [sym],
                )
            )
    return out


SYSTEM_PROMPT = """You explain portfolio metrics for a paper-trading demo app covering Indian equities. \
The user's message is a JSON object of metrics already calculated by the app from simulated data, \
plus the rule-based observations the app produced.

Write a short summary (at most 120 words) in plain English for a retail investor who is new to these terms.
- Use only numbers that appear in the JSON. Do not introduce prices, company results, news, market events or forecasts.
- Do not tell the user to buy, sell or hold anything, and do not give personalised advice.
- Use ₹ for amounts. Plain prose, no headings or bullet points."""

_summary_cache: dict[str, str] = {}


def llm_summary(metrics: dict, insights: list[Insight], settings: Settings) -> tuple[str | None, str | None]:
    """Return (summary, error). Never raises; the caller falls back to rules on error."""
    payload = json.dumps({"metrics": metrics, "observations": [i.text for i in insights]}, sort_keys=True)
    key = hashlib.sha256(f"{settings.anthropic_model}:{payload}".encode()).hexdigest()
    if key in _summary_cache:
        return _summary_cache[key], None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=45.0, max_retries=1)
    extra = {}
    if settings.anthropic_model in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        response = client.beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": payload}],
            **extra,
        )
    except anthropic.AuthenticationError:
        return None, "The configured Anthropic API key was rejected."
    except anthropic.RateLimitError:
        return None, "The AI service is rate-limited; showing rule-based insights."
    except anthropic.APIStatusError as e:
        log.warning("Anthropic API error %s: %s", e.status_code, e.message)
        return None, f"The AI service returned an error ({e.status_code})."
    except anthropic.APIConnectionError:
        return None, "Could not reach the AI service."

    if response.stop_reason == "refusal":
        return None, "The AI service declined this request."
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        return None, "The AI service returned an empty response."
    if len(_summary_cache) > 64:
        _summary_cache.clear()
    _summary_cache[key] = text
    return text, None


def insight_dicts(insights: list[Insight]) -> list[dict]:
    return [asdict(i) for i in insights]
