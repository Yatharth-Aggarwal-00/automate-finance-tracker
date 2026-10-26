from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://finance:finance@localhost:5433/finance"

    # Paper trading
    initial_cash: Decimal = Decimal("100000.00")
    paper_fee_percent: Decimal = Decimal("0.10")  # % of order value, simulated estimate
    paper_fee_flat: Decimal = Decimal("0.00")  # flat ₹ per order, simulated estimate

    # Market data
    market_data_provider: str = "csv"  # csv | upstox
    market_data_dir: Path = BACKEND_DIR / "data" / "fixtures"
    csv_data_status: str = "SIMULATED"  # SIMULATED for generated fixtures, HISTORICAL for real EOD files
    upstox_access_token: str | None = None

    # AI insights (optional)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"

    cors_origins: str = "http://localhost:3000"

    @field_validator("anthropic_api_key", "upstox_access_token", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        return v or None

    @property
    def llm_enabled(self) -> bool:
        return self.anthropic_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
