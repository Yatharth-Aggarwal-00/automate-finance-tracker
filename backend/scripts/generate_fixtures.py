"""Generate deterministic, SIMULATED daily OHLCV fixtures.

These are NOT real market prices. They are a seeded random walk (geometric
Brownian motion) so the app, charts and tests have reproducible data without
any market-data licence or API credentials.

    python -m scripts.generate_fixtures [--end 2026-10-23] [--days 260]
"""

import argparse
import csv
import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

# symbol, name, sector, start price, annual drift, annual volatility
INSTRUMENTS = [
    ("RELIANCE", "Reliance Industries Ltd", "Energy", 1350.0, 0.08, 0.22),
    ("TCS", "Tata Consultancy Services Ltd", "Information Technology", 3400.0, 0.02, 0.20),
    ("INFY", "Infosys Ltd", "Information Technology", 1550.0, 0.05, 0.24),
    ("HDFCBANK", "HDFC Bank Ltd", "Financial Services", 900.0, 0.10, 0.18),
    ("ICICIBANK", "ICICI Bank Ltd", "Financial Services", 1300.0, 0.12, 0.21),
]


def trading_days(end: date, count: int) -> list[date]:
    """Weekdays only; no exchange-holiday calendar (documented limitation)."""
    days, d = [], end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def two_dp(x: float) -> str:
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate(end: date, count: int, seed: int = 42) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days = trading_days(end, count)
    dt = 1 / 252
    with (OUT_DIR / "instruments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name", "exchange", "sector"])
        for sym, name, sector, *_ in INSTRUMENTS:
            w.writerow([sym, name, "NSE", sector])

    for i, (sym, _name, _sector, price, mu, sigma) in enumerate(INSTRUMENTS):
        rng = random.Random(seed + i)
        close = price
        with (OUT_DIR / f"{sym}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "open", "high", "low", "close", "volume"])
            for d in days:
                open_ = close * math.exp(rng.gauss(0, sigma * math.sqrt(dt) * 0.3))
                close = close * math.exp((mu - sigma**2 / 2) * dt + sigma * math.sqrt(dt) * rng.gauss(0, 1))
                high = max(open_, close) * (1 + abs(rng.gauss(0, 0.004)))
                low = min(open_, close) * (1 - abs(rng.gauss(0, 0.004)))
                volume = int(rng.uniform(2e6, 9e6))
                w.writerow([d.isoformat(), two_dp(open_), two_dp(high), two_dp(low), two_dp(close), volume])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 23))
    p.add_argument("--days", type=int, default=260)
    args = p.parse_args()
    generate(args.end, args.days)
    print(f"Wrote {len(INSTRUMENTS)} simulated series to {OUT_DIR}")
