"""The same market data for every user: for tests, and for running without users' own keys."""

from shadowfolio.ports.market_data import MarketData, MarketDataSource


class SharedMarketData(MarketDataSource):
    def __init__(self, data: MarketData) -> None:
        self._data = data

    def for_user(self, user_id: str) -> MarketData:
        return self._data
