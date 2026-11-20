"""Tax lots (FIFO) rebuilt from the trade ledger. Pure functions.

Indian tax treats demat sales as first-in-first-out, so each sell consumes the oldest
lots first. (The portfolio view uses average cost, as brokers display it; tax uses FIFO.)
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.services.portfolio import money
from app.services.tax import RealizedGain


@dataclass(frozen=True)
class LedgerTrade:
    symbol: str
    side: str
    quantity: int
    trade_date: date
    cash_change: Decimal  # negative for buys (gross + charges), positive for sells (net proceeds)


@dataclass(frozen=True)
class Lot:
    symbol: str
    buy_date: date
    quantity: int
    cost: Decimal  # incl. buy charges

    @property
    def cost_per_share(self) -> Decimal:
        return self.cost / self.quantity


def consume_fifo(lots: list[Lot], quantity: int, sell_date: date, proceeds: Decimal) -> tuple[list[Lot], list[RealizedGain]]:
    """Sell `quantity` from `lots` (oldest first). Returns (remaining lots, realized pieces).

    Proceeds are split across pieces pro rata by quantity; rounding residue goes to the last piece
    so the pieces always sum exactly to `proceeds`.
    """
    if quantity > sum(l.quantity for l in lots):
        raise ValueError("Selling more shares than the lots hold")
    remaining, pieces, left, proceeds_left = list(lots), [], quantity, proceeds
    while left:
        lot = remaining[0]
        q = min(left, lot.quantity)
        cost = lot.cost if q == lot.quantity else money(lot.cost * q / lot.quantity)
        left -= q
        piece_proceeds = proceeds_left if left == 0 else money(proceeds * q / quantity)
        proceeds_left -= piece_proceeds
        pieces.append(RealizedGain(lot.symbol, lot.buy_date, sell_date, q, cost, piece_proceeds))
        if q == lot.quantity:
            remaining.pop(0)
        else:
            remaining[0] = replace(lot, quantity=lot.quantity - q, cost=lot.cost - cost)
    return remaining, pieces


def replay(trades: Iterable[LedgerTrade]) -> tuple[dict[str, list[Lot]], list[RealizedGain]]:
    """Replay trades in date order. Returns (open lots per symbol, all realized gains)."""
    lots: dict[str, list[Lot]] = {}
    realized: list[RealizedGain] = []
    for t in sorted(trades, key=lambda t: t.trade_date):
        if t.side == "BUY":
            lots.setdefault(t.symbol, []).append(Lot(t.symbol, t.trade_date, t.quantity, -t.cash_change))
        else:
            lots[t.symbol], pieces = consume_fifo(lots.get(t.symbol, []), t.quantity, t.trade_date, t.cash_change)
            realized.extend(pieces)
    return {s: l for s, l in lots.items() if l}, realized
