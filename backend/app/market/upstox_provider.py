from datetime import date

from app.market.base import Candle, DataStatus, InstrumentInfo, MarketDataUnavailable, Quote


class UpstoxProvider:
    """Placeholder for the Upstox Developer API (see README, "Market data").

    Not implemented in this POC: access needs an Upstox account, a registered app
    and an OAuth access token that expires daily, and the usage terms must be
    reviewed before use. Implement these three methods against the official API
    and keep MARKET_DATA_PROVIDER=csv until then.
    """

    source = "upstox"
    status = DataStatus.HISTORICAL

    def __init__(self, access_token: str | None):
        if not access_token:
            raise MarketDataUnavailable("MARKET_DATA_PROVIDER=upstox requires UPSTOX_ACCESS_TOKEN")
        self.access_token = access_token

    def _not_implemented(self):
        raise MarketDataUnavailable("Upstox adapter is not implemented in this POC; use MARKET_DATA_PROVIDER=csv")

    def list_instruments(self, query: str | None = None) -> list[InstrumentInfo]:
        self._not_implemented()

    def get_quote(self, symbol: str) -> Quote:
        self._not_implemented()

    def get_history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Candle]:
        self._not_implemented()
