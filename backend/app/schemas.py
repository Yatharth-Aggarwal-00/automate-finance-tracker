from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

# Decimals are exact internally and in the DB; JSON carries them as numbers.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
DataStatusStr = Literal["LIVE", "DELAYED", "HISTORICAL", "SIMULATED"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    order_id: int | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    market_data_provider: str
    llm_enabled: bool


class StockOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    sector: str
    price: Money | None
    previous_close: Money | None
    change: Money | None
    change_pct: float | None
    as_of: datetime | None
    data_status: DataStatusStr
    data_source: str


class IndicatorsOut(BaseModel):
    sma20: float | None = Field(description="20-day simple moving average; null if < 20 closes")
    sma50: float | None = Field(description="50-day simple moving average; null if < 50 closes")
    rsi14: float | None = Field(description="Wilder's 14-day RSI; null if < 15 closes")
    volatility_20d: float | None = Field(description="Annualised std-dev of the last 20 daily log returns, %")


class QuoteOut(StockOut):
    indicators: IndicatorsOut
    history_points: int


class CandleOut(BaseModel):
    date: date
    open: Money
    high: Money
    low: Money
    close: Money
    volume: int
    sma20: float | None
    sma50: float | None
    rsi14: float | None


class HistoryOut(BaseModel):
    symbol: str
    data_status: DataStatusStr
    data_source: str
    as_of: datetime | None
    candles: list[CandleOut]


class HoldingOut(BaseModel):
    symbol: str
    name: str
    sector: str
    quantity: int
    avg_cost: Money
    cost_basis: Money
    price: Money
    market_value: Money
    unrealized_pnl: Money
    unrealized_pnl_pct: Money
    weight_pct: float
    price_as_of: datetime | None


class PortfolioOut(BaseModel):
    initial_cash: Money
    cash: Money
    invested: Money = Field(description="Cost basis of open positions, including estimated buy charges")
    market_value: Money
    total_value: Money
    unrealized_pnl: Money
    realized_pnl: Money
    total_pnl: Money
    return_pct: Money
    holdings: list[HoldingOut]
    data_status: DataStatusStr
    as_of: datetime | None
    fee_percent: Money
    fee_flat: Money


class PortfolioPointOut(BaseModel):
    date: date
    cash: Money
    market_value: Money
    total_value: Money


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    price: Money
    gross_amount: Money
    fees: Money
    cash_change: Money
    realized_pnl: Money | None
    price_date: date
    executed_at: datetime


class OrderIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9&\-]{1,32}$", examples=["TCS"])
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, le=100_000, description="Whole shares")

    @field_validator("symbol", "side", mode="before")
    @classmethod
    def upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class OrderPreviewOut(BaseModel):
    simulated: Literal[True] = True
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    price: Money
    price_date: date
    gross_amount: Money
    fees: Money = Field(description="Simulated charges estimate, not actual brokerage")
    cash_change: Money
    cash_after: Money
    position_quantity_after: int
    realized_pnl: Money | None
    fee_note: str


class OrderOut(BaseModel):
    id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    status: Literal["EXECUTED", "REJECTED"]
    reject_code: str | None
    reject_reason: str | None
    created_at: datetime
    trade: TradeOut | None


class OrderResultOut(BaseModel):
    simulated: Literal[True] = True
    replayed: bool = Field(description="True if this Idempotency-Key was already processed")
    order: OrderOut
    cash: Money


class InsightOut(BaseModel):
    kind: str
    severity: Literal["info", "attention"]
    title: str
    text: str
    symbols: list[str]


class InsightsOut(BaseModel):
    generated_by: Literal["rules", "rules+llm"]
    model: str | None
    summary: str | None
    llm_error: str | None
    disclaimer: str
    insights: list[InsightOut]
    metrics: dict
    data_status: DataStatusStr
    as_of: datetime | None
