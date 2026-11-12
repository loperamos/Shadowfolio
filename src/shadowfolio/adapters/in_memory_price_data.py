"""PriceData holding quotes in memory, for tests."""

from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData


class InMemoryPriceData(PriceData):
    def __init__(self, quotes: dict[str, Quote] | None = None) -> None:
        self._quotes = dict(quotes or {})

    def set(self, symbol: str, quote: Quote) -> None:
        self._quotes[symbol] = quote

    def latest_price(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)
