"""Pure, deterministic portfolio math. No database access.

Accounting model:
- A position tracks `quantity` and `cost_basis` (total ₹ paid for the shares still
  held, including estimated buy charges). Average cost = cost_basis / quantity.
- Selling removes a proportional slice of cost basis; realized P&L is the net
  proceeds (after estimated sell charges) minus that slice.
- With this model, total P&L == realized + unrealized == portfolio value - initial cash,
  exactly, to the paisa.
"""

from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

PAISA = Decimal("0.01")
ZERO = Decimal("0.00")


def money(x: Decimal | int | str) -> Decimal:
    return Decimal(x).quantize(PAISA, rounding=ROUND_HALF_UP)


def inr(x: Decimal) -> str:
    """Format with Indian digit grouping: 100000 -> ₹1,00,000.00."""
    sign = "-" if x < 0 else ""
    whole, frac = f"{abs(money(x)):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return f"{sign}₹{whole}.{frac}"


class TradingError(Exception):
    code = "TRADING_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InsufficientCash(TradingError):
    code = "INSUFFICIENT_CASH"


class InsufficientHoldings(TradingError):
    code = "INSUFFICIENT_HOLDINGS"


@dataclass(frozen=True)
class Position:
    quantity: int
    cost_basis: Decimal

    @property
    def avg_cost(self) -> Decimal:
        return (self.cost_basis / self.quantity).quantize(PAISA, rounding=ROUND_HALF_UP) if self.quantity else ZERO


@dataclass(frozen=True)
class OrderCalc:
    side: str
    quantity: int
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    cash_change: Decimal  # signed: negative for buys
    cash_after: Decimal
    position_after: Position | None
    realized_pnl: Decimal | None


def estimate_fees(gross: Decimal, fee_percent: Decimal, fee_flat: Decimal) -> Decimal:
    """Simulated brokerage/charges estimate. Not a model of real statutory charges."""
    return money(gross * fee_percent / 100 + fee_flat)


def calculate_order(
    side: str,
    quantity: int,
    price: Decimal,
    cash: Decimal,
    position: Position | None,
    fee_percent: Decimal,
    fee_flat: Decimal,
) -> OrderCalc:
    """Validate and price an order. Raises TradingError subclasses; never mutates input."""
    if quantity <= 0:
        raise TradingError("Quantity must be a positive whole number")
    if price <= 0:
        raise TradingError("Price must be positive")
    gross = money(price * quantity)
    fees = estimate_fees(gross, fee_percent, fee_flat)

    if side == "BUY":
        total = gross + fees
        if total > cash:
            raise InsufficientCash(
                f"Order needs {inr(total)} including estimated charges; available cash is {inr(cash)}"
            )
        held = position or Position(0, ZERO)
        new_pos = Position(held.quantity + quantity, held.cost_basis + total)
        return OrderCalc(side, quantity, price, gross, fees, -total, cash - total, new_pos, None)

    if side == "SELL":
        held_qty = position.quantity if position else 0
        if quantity > held_qty:
            raise InsufficientHoldings(f"Cannot sell {quantity} shares; you hold {held_qty}")
        assert position is not None
        proceeds = gross - fees
        if quantity == position.quantity:
            cost_removed, new_pos = position.cost_basis, None
        else:
            cost_removed = money(position.cost_basis * quantity / position.quantity)
            new_pos = Position(position.quantity - quantity, position.cost_basis - cost_removed)
        return OrderCalc(side, quantity, price, gross, fees, proceeds, cash + proceeds, new_pos, proceeds - cost_removed)

    raise TradingError("Side must be BUY or SELL")


@dataclass(frozen=True)
class HoldingValuation:
    symbol: str
    quantity: int
    avg_cost: Decimal
    cost_basis: Decimal
    price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal


@dataclass(frozen=True)
class PortfolioSummary:
    initial_cash: Decimal
    cash: Decimal
    invested: Decimal  # cost basis of open positions
    market_value: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    return_pct: Decimal
    holdings: list[HoldingValuation]


def pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return money(numerator / denominator * 100) if denominator else ZERO


def value_holding(symbol: str, pos: Position, price: Decimal) -> HoldingValuation:
    mv = money(price * pos.quantity)
    unrealized = mv - pos.cost_basis
    return HoldingValuation(
        symbol, pos.quantity, pos.avg_cost, pos.cost_basis, price, mv, unrealized, pct(unrealized, pos.cost_basis)
    )


def summarize(
    initial_cash: Decimal,
    cash: Decimal,
    positions: Iterable[tuple[str, Position, Decimal]],
    realized_pnl: Decimal,
) -> PortfolioSummary:
    holdings = [value_holding(sym, pos, price) for sym, pos, price in positions]
    invested = sum((h.cost_basis for h in holdings), ZERO)
    market_value = sum((h.market_value for h in holdings), ZERO)
    total_value = cash + market_value
    total_pnl = total_value - initial_cash
    return PortfolioSummary(
        initial_cash=initial_cash,
        cash=cash,
        invested=invested,
        market_value=market_value,
        total_value=total_value,
        unrealized_pnl=market_value - invested,
        realized_pnl=realized_pnl,
        total_pnl=total_pnl,
        return_pct=pct(total_pnl, initial_cash),
        holdings=holdings,
    )


@dataclass(frozen=True)
class LedgerEntry:
    price_date: date
    symbol: str
    side: str
    quantity: int
    cash_change: Decimal


@dataclass(frozen=True)
class ValuePoint:
    date: date
    cash: Decimal
    market_value: Decimal
    total_value: Decimal


def portfolio_history(
    initial_cash: Decimal,
    ledger: Sequence[LedgerEntry],
    closes: Mapping[str, Mapping[date, Decimal]],
    dates: Sequence[date],
) -> list[ValuePoint]:
    """Rebuild end-of-day portfolio value for each date by replaying the trade ledger.

    A trade affects a day's value if it was filled on or before that day's bar.
    Missing closes carry forward the last known close for that symbol.
    """
    entries = sorted(ledger, key=lambda e: e.price_date)
    sorted_closes = {s: sorted(c.items()) for s, c in closes.items()}
    cash, qty, i, points = initial_cash, {}, 0, []
    for d in dates:
        while i < len(entries) and entries[i].price_date <= d:
            e = entries[i]
            cash += e.cash_change
            qty[e.symbol] = qty.get(e.symbol, 0) + (e.quantity if e.side == "BUY" else -e.quantity)
            i += 1
        mv = ZERO
        for sym, q in qty.items():
            if q:
                series = sorted_closes.get(sym, [])
                idx = bisect_right(series, (d, Decimal("Infinity"))) - 1
                if idx >= 0:
                    mv += money(series[idx][1] * q)
        points.append(ValuePoint(d, cash, mv, cash + mv))
    return points
