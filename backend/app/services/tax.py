"""Indian capital-gains tax on listed equity shares (STT-paid), FY 2026-27 rules. Pure functions.

- Short-term (held 12 months or less): 20% (Sec 111A).
- Long-term (held more than 12 months): 12.5% on gains above ₹1.25 lakh per financial year (Sec 112A).
- 4% health & education cess on the tax. Surcharge is ignored (it only applies at high incomes).
- Set-off within a year: short-term losses offset short-term then long-term gains; long-term
  losses offset only long-term gains. Carry-forward of losses is not modelled.

This is an estimate for decision support, not tax advice. Rates were checked against FY 2026-27
sources (Budget 2026 left them unchanged); review them each Budget.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.services.portfolio import ZERO, money

STCG_RATE = Decimal("0.20")
LTCG_RATE = Decimal("0.125")
LTCG_EXEMPTION = Decimal("125000.00")
CESS = Decimal("0.04")


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb in a non-leap target year
        return d.replace(year=d.year + years, day=28)


def long_term_from(buy_date: date) -> date:
    """First sale date that counts as 'held for more than 12 months' (conservative: anniversary + 1 day)."""
    return add_years(buy_date, 1) + timedelta(days=1)


def is_long_term(buy_date: date, sell_date: date) -> bool:
    return sell_date >= long_term_from(buy_date)


def financial_year(d: date) -> tuple[date, date]:
    """Indian FY: 1 April to 31 March."""
    start_year = d.year if d.month >= 4 else d.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def fy_label(d: date) -> str:
    start, end = financial_year(d)
    return f"FY {start.year}-{str(end.year)[-2:]}"


@dataclass(frozen=True)
class RealizedGain:
    symbol: str
    buy_date: date
    sell_date: date
    quantity: int
    cost: Decimal  # cost of the shares sold, incl. buy charges
    proceeds: Decimal  # sale value net of sell charges

    @property
    def gain(self) -> Decimal:
        return self.proceeds - self.cost

    @property
    def long_term(self) -> bool:
        return is_long_term(self.buy_date, self.sell_date)


@dataclass(frozen=True)
class TaxEstimate:
    short_term_net: Decimal  # after set-off
    long_term_net: Decimal  # after set-off, before exemption
    exemption_used: Decimal
    exemption_remaining: Decimal
    taxable_short_term: Decimal
    taxable_long_term: Decimal
    tax: Decimal  # including cess


def estimate_tax(gains: Iterable[RealizedGain]) -> TaxEstimate:
    """Tax for one financial year's realized gains."""
    gains = list(gains)
    st = sum((g.gain for g in gains if not g.long_term), ZERO)
    lt = sum((g.gain for g in gains if g.long_term), ZERO)
    if st < 0:  # short-term loss can offset long-term gains
        lt, st = lt + st, ZERO
    taxable_st = max(st, ZERO)
    lt_positive = max(lt, ZERO)
    exemption_used = min(lt_positive, LTCG_EXEMPTION)
    taxable_lt = lt_positive - exemption_used
    tax = money((taxable_st * STCG_RATE + taxable_lt * LTCG_RATE) * (1 + CESS))
    return TaxEstimate(
        short_term_net=st,
        long_term_net=lt,
        exemption_used=exemption_used,
        exemption_remaining=LTCG_EXEMPTION - exemption_used,
        taxable_short_term=taxable_st,
        taxable_long_term=taxable_lt,
        tax=tax,
    )
