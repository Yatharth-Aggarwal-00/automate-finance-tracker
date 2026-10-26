from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import health, insights, paper_trades, portfolio, stocks
from app.services.market import PriceUnavailable, UnknownSymbol
from app.services.portfolio import TradingError
from app.services.trading import OrderRejected

app = FastAPI(
    title="AI Investment Intelligence POC",
    version="0.1.0",
    description=(
        "Paper-trading portfolio tracker for Indian equities. **SIMULATION ONLY**: no real money, "
        "no broker connection, no live orders. Bundled market data is simulated unless stated otherwise."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message, **extra}})


@app.exception_handler(OrderRejected)
def order_rejected(_: Request, exc: OrderRejected):
    return _error(400, exc.error.code, exc.error.message, order_id=exc.order.id)


@app.exception_handler(TradingError)
def trading_error(_: Request, exc: TradingError):
    status = 404 if isinstance(exc, UnknownSymbol) else 503 if isinstance(exc, PriceUnavailable) else 400
    return _error(status, exc.code, exc.message)


for r in (health, stocks, portfolio, paper_trades, insights):
    app.include_router(r.router)
