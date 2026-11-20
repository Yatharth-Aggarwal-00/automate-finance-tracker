from app.config import Settings
from app.market.base import DataStatus, MarketDataProvider, MarketDataUnavailable
from app.market.csv_provider import CsvProvider
from app.market.upstox_provider import UpstoxProvider
from app.market.yahoo_provider import YahooProvider


def get_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_data_provider == "csv":
        return CsvProvider(settings.market_data_dir, DataStatus(settings.csv_data_status))
    if settings.market_data_provider == "yahoo":
        return YahooProvider(settings.universe_file, settings.history_start)
    if settings.market_data_provider == "upstox":
        return UpstoxProvider(settings.upstox_access_token)
    raise MarketDataUnavailable(f"Unknown MARKET_DATA_PROVIDER: {settings.market_data_provider}")


def fallback_provider(settings: Settings) -> MarketDataProvider:
    """Bundled simulated data, used only when the configured provider fails and the DB is empty."""
    return CsvProvider(settings.market_data_dir, DataStatus.SIMULATED)
