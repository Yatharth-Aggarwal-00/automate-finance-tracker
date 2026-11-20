"""Decision checks shown before a trade, and the tax & timing summary.

Facts and arithmetic only: tax consequences, historical risk, concentration and trading
activity. Nothing here predicts prices or says what to buy or sell.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.market.yahoo_provider import IST
from app.models import Trade
from app.services.lots import LedgerTrade, Lot, consume_fifo, replay
from app.services.market import get_instrument, latest_prices, price_history
from app.services.portfolio import ZERO, inr, money
from app.services.reports import build_report
from app.services.risk import (
    TRADING_DAYS_PER_MONTH,
    TRADING_DAYS_PER_YEAR,
    Drawdown,
    WindowReturn,
    annual_volatility,
    max_drawdown,
    share_of_losing_windows,
    worst_window,
)
from app.services.tax import (
    RealizedGain,
    TaxEstimate,
    add_years,
    estimate_tax,
    financial_year,
    fy_label,
    long_term_from,
)
from app.services.trading import get_account, preview_order

WAIT_WINDOW_DAYS = 60  # only suggest waiting if long-term status is this close
POSITION_LIMIT_PCT = 20
SECTOR_LIMIT_PCT = 40
BUSY_TRADES_30D = 10
RISK_LOOKBACK_YEARS = 5


def today_ist() -> date:
    return datetime.now(IST).date()


def load_ledger(db: Session, account_id: int) -> list[LedgerTrade]:
    trades = db.scalars(
        select(Trade)
        .options(joinedload(Trade.instrument))
        .where(Trade.account_id == account_id)
        .order_by(Trade.executed_at, Trade.id)
    )
    return [
        LedgerTrade(t.instrument.symbol, t.side, t.quantity, t.executed_at.astimezone(IST).date(), t.cash_change)
        for t in trades
    ]


def fy_realized(realized: list[RealizedGain], on: date) -> list[RealizedGain]:
    start, end = financial_year(on)
    return [g for g in realized if start <= g.sell_date <= end]


def incremental_tax(base: list[RealizedGain], extra: list[RealizedGain]) -> Decimal:
    return estimate_tax(base + extra).tax - estimate_tax(base).tax


# ---------------------------------------------------------------- sell check


@dataclass(frozen=True)
class SellOption:
    label: str
    quantity: int
    sell_date: date
    tax: Decimal
    saving: Decimal


@dataclass(frozen=True)
class SellCheck:
    symbol: str
    quantity: int
    price: Decimal
    proceeds: Decimal
    sell_date: date
    fy: str
    pieces: list[RealizedGain]
    tax: Decimal  # extra tax this sale adds to the FY
    gain: Decimal
    fy_before: TaxEstimate
    fy_after: TaxEstimate
    options: list[SellOption] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def sell_check(db: Session, settings: Settings, symbol: str, quantity: int, today: date | None = None) -> SellCheck:
    today = today or today_ist()
    preview = preview_order(db, settings, symbol, "SELL", quantity)  # validates holdings and price
    sym = preview.instrument.symbol
    proceeds = preview.calc.cash_change
    lots, realized = replay(load_ledger(db, get_account(db).id))
    base = fy_realized(realized, today)
    _, pieces = consume_fifo(lots.get(sym, []), quantity, today, proceeds)
    tax_now = incremental_tax(base, pieces)

    options: list[SellOption] = []
    short_gains = [p for p in pieces if not p.long_term and p.gain > 0]
    if short_gains:
        # Option 1: wait until every lot in this sale is long-term (same price assumed).
        until = max(long_term_from(p.buy_date) for p in short_gains)
        if (until - today).days <= WAIT_WINDOW_DAYS:
            later = [replace(p, sell_date=until) for p in pieces]
            later_base = fy_realized(realized, until)
            tax_then = incremental_tax(later_base, later)
            if tax_then < tax_now:
                options.append(
                    SellOption(f"Wait until {until:%d %b %Y}", quantity, until, tax_then, tax_now - tax_then)
                )
        # Option 2: sell only the shares that are already long-term now.
        lt_qty = sum(p.quantity for p in pieces if p.long_term)
        if 0 < lt_qty < quantity:
            part_proceeds = money(proceeds * lt_qty / quantity)
            _, part = consume_fifo(lots[sym], lt_qty, today, part_proceeds)
            tax_part = incremental_tax(base, part)
            options.append(
                SellOption(
                    "Sell only the long-term shares now",
                    lt_qty,
                    today,
                    tax_part,
                    ZERO,  # not comparable: fewer shares sold
                )
            )

    notes = sell_notes(pieces, today, options)
    return SellCheck(
        symbol=sym,
        quantity=quantity,
        price=preview.calc.price,
        proceeds=proceeds,
        sell_date=today,
        fy=fy_label(today),
        pieces=pieces,
        tax=tax_now,
        gain=sum((p.gain for p in pieces), ZERO),
        fy_before=estimate_tax(base),
        fy_after=estimate_tax(base + pieces),
        options=options,
        notes=notes,
    )


def sell_notes(pieces: list[RealizedGain], today: date, options: list[SellOption]) -> list[str]:
    notes: list[str] = []
    st_loss = [p for p in pieces if not p.long_term and p.gain < 0]
    st_gain = [p for p in pieces if not p.long_term and p.gain > 0]
    if st_loss:
        loss = -sum((p.gain for p in st_loss), ZERO)
        turns = min(long_term_from(p.buy_date) for p in st_loss)
        line = (
            f"This books a short-term loss of {inr(loss)}. Short-term losses can offset both short- and "
            "long-term gains this year"
        )
        if (turns - today).days <= WAIT_WINDOW_DAYS:
            line += f"; from {turns:%d %b %Y} it would be a long-term loss, usable only against long-term gains"
        notes.append(line + ".")
    elif any(p.gain < 0 for p in pieces):
        notes.append("This books a long-term loss, which can only offset long-term gains.")
    if any(p.gain < 0 for p in pieces):
        notes.append("Unused capital losses can be carried forward for 8 years if you file your tax return on time.")
    if st_gain and not any(o.saving > 0 for o in options):
        turns = max(long_term_from(p.buy_date) for p in st_gain)
        notes.append(
            f"Short-term gain, taxed at 20% plus cess. These shares are long-term from {turns:%d %b %Y} "
            f"({(turns - today).days} days)."
        )
    return notes


# ---------------------------------------------------------------- buy check


@dataclass(frozen=True)
class Flag:
    kind: str  # position | sector | activity | drawdown | tax
    level: str  # info | attention
    text: str


@dataclass(frozen=True)
class BuyCheck:
    symbol: str
    quantity: int
    amount: Decimal  # total debit incl. charges
    history_years: float
    drawdown: Drawdown | None
    drawdown_rupees: Decimal | None  # what `amount` would have lost through that fall
    worst_month: WindowReturn | None
    worst_month_rupees: Decimal | None
    losing_year_pct: float | None  # % of 1-year holding periods that lost money
    volatility_1y: float | None
    position_pct_after: float
    sector: str
    sector_pct_after: float
    trades_30d: int
    charges_fy: Decimal
    flags: list[Flag]


def buy_check(db: Session, settings: Settings, symbol: str, quantity: int, today: date | None = None) -> BuyCheck:
    today = today or today_ist()
    preview = preview_order(db, settings, symbol, "BUY", quantity)  # validates cash and price
    inst = preview.instrument
    amount = -preview.calc.cash_change

    bars = price_history(db, inst.id)
    cutoff = add_years(today, -RISK_LOOKBACK_YEARS)
    recent = [b for b in bars if b.date >= cutoff]
    dates, closes = [b.date for b in recent], [float(b.close) for b in recent]
    dd = max_drawdown(dates, closes)
    wm = worst_window(dates, closes, TRADING_DAYS_PER_MONTH)
    years = round(len(recent) / TRADING_DAYS_PER_YEAR, 1)

    report = build_report(db)
    s = report.summary
    total_after = s.total_value - preview.calc.fees  # buying moves cash into shares; only charges leave
    existing = next((h for h in s.holdings if h.symbol == inst.symbol), None)
    position_after = (existing.market_value if existing else ZERO) + preview.calc.gross_amount
    sector_after = preview.calc.gross_amount + sum(
        (h.market_value for h in s.holdings if report.instruments[h.symbol].sector == inst.sector), ZERO
    )
    pct = lambda x: round(float(x / total_after * 100), 1) if total_after else 0.0  # noqa: E731

    account = get_account(db)
    ledger = load_ledger(db, account.id)
    trades_30d = sum(1 for t in ledger if t.trade_date > today - timedelta(days=30))
    fy_start, fy_end = financial_year(today)
    charges_fy = sum(
        (
            t.fees
            for t in db.scalars(select(Trade).where(Trade.account_id == account.id))
            if fy_start <= t.executed_at.astimezone(IST).date() <= fy_end
        ),
        ZERO,
    )

    flags: list[Flag] = []
    position_pct, sector_pct = pct(position_after), pct(sector_after)
    if position_pct > POSITION_LIMIT_PCT:
        flags.append(Flag("position", "attention", f"After this buy, {inst.symbol} would be {position_pct}% of your portfolio."))
    if sector_pct > SECTOR_LIMIT_PCT:
        flags.append(Flag("sector", "attention", f"{inst.sector} would be {sector_pct}% of your portfolio after this buy."))
    if trades_30d >= BUSY_TRADES_30D:
        flags.append(
            Flag(
                "activity",
                "attention",
                f"You've placed {trades_30d} trades in the last 30 days. SEBI's studies found loss-making "
                "traders trade more often, and charges deepen losses.",
            )
        )
    if dd and dd.pct <= -40:
        flags.append(Flag("drawdown", "attention", f"{inst.symbol} has fallen {abs(dd.pct):.0f}% from a peak within the last {years:g} years."))
    flags.append(
        Flag(
            "tax",
            "info",
            "If you sell within 12 months, gains are taxed at 20% (plus cess); after 12 months at 12.5% "
            "above the yearly ₹1.25 lakh exemption.",
        )
    )

    return BuyCheck(
        symbol=inst.symbol,
        quantity=quantity,
        amount=amount,
        history_years=years,
        drawdown=dd,
        drawdown_rupees=money(amount * Decimal(str(dd.pct)) / 100) if dd else None,
        worst_month=wm,
        worst_month_rupees=money(amount * Decimal(str(wm.pct)) / 100) if wm else None,
        losing_year_pct=share_of_losing_windows(closes, TRADING_DAYS_PER_YEAR),
        volatility_1y=annual_volatility(closes),
        position_pct_after=position_pct,
        sector=inst.sector,
        sector_pct_after=sector_pct,
        trades_30d=trades_30d,
        charges_fy=charges_fy,
        flags=flags,
    )


# ---------------------------------------------------------------- tax summary


@dataclass(frozen=True)
class OpenLot:
    lot: Lot
    price: Decimal
    market_value: Decimal
    unrealized_gain: Decimal
    long_term_from: date
    days_to_long_term: int  # 0 if already long-term
    extra_tax_if_sold_today: Decimal  # vs. selling on the long-term date; 0 if not applicable


@dataclass(frozen=True)
class TaxSummary:
    fy: str
    fy_end: date
    days_left_in_fy: int
    realized: list[RealizedGain]
    estimate: TaxEstimate
    lots: list[OpenLot]
    harvestable_ltcg: Decimal  # long-term gains that could still be booked tax-free this FY
    unrealized_long_term_gain: Decimal


def tax_summary(db: Session, today: date | None = None) -> TaxSummary:
    today = today or today_ist()
    lots_by_symbol, realized = replay(load_ledger(db, get_account(db).id))
    base = fy_realized(realized, today)
    est = estimate_tax(base)
    _, fy_end = financial_year(today)

    symbols = list(lots_by_symbol)
    prices = {}
    if symbols:
        ids = {get_instrument(db, s).id: s for s in symbols}
        prices = {ids[i]: lp.price for i, lp in latest_prices(db, list(ids)).items()}

    open_lots: list[OpenLot] = []
    for sym, lots in lots_by_symbol.items():
        price = prices.get(sym)
        if price is None:
            continue
        for lot in lots:
            mv = money(price * lot.quantity)
            gain = mv - lot.cost
            lt_from = long_term_from(lot.buy_date)
            days = max(0, (lt_from - today).days)
            extra = ZERO
            if days and gain > 0:
                piece_now = RealizedGain(sym, lot.buy_date, today, lot.quantity, lot.cost, mv)
                extra = incremental_tax(base, [piece_now]) - incremental_tax(
                    fy_realized(realized, lt_from), [replace(piece_now, sell_date=lt_from)]
                )
            open_lots.append(OpenLot(lot, price, mv, gain, lt_from, days, max(extra, ZERO)))

    unrealized_lt = sum((l.unrealized_gain for l in open_lots if l.days_to_long_term == 0 and l.unrealized_gain > 0), ZERO)
    return TaxSummary(
        fy=fy_label(today),
        fy_end=fy_end,
        days_left_in_fy=(fy_end - today).days,
        realized=base,
        estimate=est,
        lots=sorted(open_lots, key=lambda l: (l.days_to_long_term == 0, l.days_to_long_term, l.lot.symbol)),
        harvestable_ltcg=min(est.exemption_remaining, unrealized_lt),
        unrealized_long_term_gain=unrealized_lt,
    )
