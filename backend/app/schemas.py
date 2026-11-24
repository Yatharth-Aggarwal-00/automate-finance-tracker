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


# ---- Decision checks & tax ----------------------------------------------------------------


class CheckIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9&\-]{1,32}$", examples=["TCS"])
    quantity: int = Field(gt=0, le=100_000, description="Whole shares")

    @field_validator("symbol", mode="before")
    @classmethod
    def upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class RealizedPieceOut(BaseModel):
    symbol: str
    buy_date: date
    sell_date: date
    quantity: int
    cost: Money
    proceeds: Money
    gain: Money
    long_term: bool
    long_term_from: date


class TaxEstimateOut(BaseModel):
    short_term_net: Money
    long_term_net: Money
    exemption_used: Money
    exemption_remaining: Money
    taxable_short_term: Money
    taxable_long_term: Money
    tax: Money = Field(description="Estimated tax incl. 4% cess; surcharge ignored")


class SellOptionOut(BaseModel):
    label: str
    quantity: int
    sell_date: date
    tax: Money
    saving: Money


class SellCheckOut(BaseModel):
    symbol: str
    quantity: int
    price: Money
    proceeds: Money
    sell_date: date
    fy: str
    pieces: list[RealizedPieceOut] = Field(description="Lots sold, oldest first (FIFO)")
    gain: Money
    tax: Money = Field(description="Extra tax this sale adds to the financial year")
    fy_before: TaxEstimateOut
    fy_after: TaxEstimateOut
    options: list[SellOptionOut]
    notes: list[str]
    disclaimer: str


class FlagOut(BaseModel):
    kind: Literal["position", "sector", "activity", "drawdown", "tax"]
    level: Literal["info", "attention"]
    text: str


class BuyCheckOut(BaseModel):
    symbol: str
    quantity: int
    amount: Money
    history_years: float
    max_drawdown_pct: float | None
    max_drawdown_peak: date | None
    max_drawdown_trough: date | None
    max_drawdown_rupees: Money | None
    worst_month_pct: float | None
    worst_month_start: date | None
    worst_month_rupees: Money | None
    losing_year_pct: float | None = Field(description="% of 1-year holding periods in the window that lost money")
    volatility_1y: float | None
    position_pct_after: float
    sector: str
    sector_pct_after: float
    trades_30d: int
    charges_fy: Money
    flags: list[FlagOut]
    disclaimer: str


class OpenLotOut(BaseModel):
    symbol: str
    buy_date: date
    quantity: int
    cost: Money
    price: Money
    market_value: Money
    unrealized_gain: Money
    long_term_from: date
    days_to_long_term: int
    extra_tax_if_sold_today: Money


class TaxRatesOut(BaseModel):
    stcg_pct: float
    ltcg_pct: float
    ltcg_exemption: Money
    cess_pct: float


class TaxSummaryOut(BaseModel):
    fy: str
    fy_end: date
    days_left_in_fy: int
    realized: list[RealizedPieceOut]
    estimate: TaxEstimateOut
    lots: list[OpenLotOut]
    harvestable_ltcg: Money
    unrealized_long_term_gain: Money
    rates: TaxRatesOut
    disclaimer: str


# ---- Quant research engine ------------------------------------------------------------------


class FactorStatsOut(BaseModel):
    months: int
    ic_mean: float | None = Field(description="Mean monthly rank IC (Spearman) with next-month returns")
    ic_t: float | None = Field(description="t-statistic of the mean IC; |t| >= 2 is the usual bar")
    hit_rate: float | None = Field(description="% of months with a positive IC")
    spread_annual: float | None = Field(description="Top minus bottom bucket return, annualised %")
    bucket_returns: list[float] = Field(description="Mean monthly % return per bucket, lowest factor values first")


class FactorOut(BaseModel):
    key: str
    name: str
    description: str
    hypothesis: str
    full: FactorStatsOut
    train: FactorStatsOut
    test: FactorStatsOut
    verdict: str


class FactorsOut(BaseModel):
    universe_size: int
    start: date
    end: date
    rebalances: int
    test_start: date
    benchmark: str | None
    data_source: str
    factors: list[FactorOut]
    caveats: list[str]


class BacktestIn(BaseModel):
    weights: dict[str, float] = Field(examples=[{"mom_12_1": 1, "low_vol": 1}], min_length=1, max_length=10)
    top_n: int = Field(15, ge=5, le=50)
    cost_bps: float = Field(20, ge=0, le=200, description="Cost per side in basis points (20 = 0.20%)")

    @field_validator("weights")
    @classmethod
    def positive(cls, v: dict[str, float]):
        if any(not (0 < w <= 10) for w in v.values()):
            raise ValueError("weights must be between 0 and 10")
        return v


class MetricsOut(BaseModel):
    months: int
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    max_drawdown: float | None
    total_return: float | None


class RelativeOut(BaseModel):
    excess_cagr: float | None
    beat_months_pct: float | None
    information_ratio: float | None


class PeriodOut(BaseModel):
    strategy: MetricsOut
    nifty: MetricsOut | None
    equal_weight: MetricsOut
    vs_nifty: RelativeOut | None
    vs_equal_weight: RelativeOut
    avg_turnover: float | None = Field(description="Average one-way monthly turnover, %")


class CurvePointOut(BaseModel):
    date: date
    strategy: float
    nifty: float | None
    equal_weight: float


class BacktestOut(BaseModel):
    weights: dict[str, float]
    top_n: int
    cost_per_side_pct: float
    risk_free_pct: float
    test_start: date
    full: PeriodOut
    train: PeriodOut
    test: PeriodOut
    curve: list[CurvePointOut]
    latest_holdings: list[str]
    latest_date: date | None
    caveats: list[str]


class ScreenIn(BaseModel):
    weights: dict[str, float] = Field(examples=[{"mom_12_1": 1, "low_vol": 1}], min_length=1, max_length=10)


class ScreenRowOut(BaseModel):
    rank: int
    symbol: str
    sector: str
    score: float
    percentiles: dict[str, float | None]


class ScreenOut(BaseModel):
    as_of: date
    weights: dict[str, float]
    rows: list[ScreenRowOut]
    disclaimer: str
