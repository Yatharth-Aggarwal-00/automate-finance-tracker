from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Instrument, PriceBar

BENCHMARK_SYMBOL = "NIFTY50"


@dataclass(frozen=True)
class Panel:
    """Daily prices: rows are trading dates, columns are symbols."""

    close: pd.DataFrame
    volume: pd.DataFrame
    benchmark: pd.Series | None  # Nifty 50 index close, aligned to `close.index`
    sectors: dict[str, str]
    source: str

    @property
    def key(self) -> tuple:
        """Changes whenever the underlying data changes; used for caching."""
        return (self.close.index[-1] if len(self.close) else None, self.close.shape, self.source)


def load_panel(db: Session) -> Panel:
    rows = db.execute(
        select(Instrument.symbol, Instrument.kind, PriceBar.date, PriceBar.close, PriceBar.volume).join(PriceBar)
    ).all()
    df = pd.DataFrame(rows, columns=["symbol", "kind", "date", "close", "volume"])
    if df.empty:
        empty = pd.DataFrame(dtype=float)
        return Panel(empty, empty, None, {}, "none")
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = df["close"].astype(float)
    eq = df[df["kind"] == "EQUITY"]
    close = eq.pivot(index="date", columns="symbol", values="close").sort_index()
    volume = eq.pivot(index="date", columns="symbol", values="volume").sort_index().reindex(close.index)
    bench = df[df["symbol"] == BENCHMARK_SYMBOL].set_index("date")["close"].sort_index()
    benchmark = bench.reindex(close.index).ffill() if not bench.empty else None
    instruments = db.execute(select(Instrument.symbol, Instrument.sector, Instrument.data_source)).all()
    sources = {i.data_source for i in instruments}
    return Panel(
        close=close,
        volume=volume.astype(float),
        benchmark=benchmark,
        sectors={i.symbol: i.sector for i in instruments},
        source=",".join(sorted(sources)),
    )
