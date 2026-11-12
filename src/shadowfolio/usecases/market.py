"""Market use cases: reading market information."""

from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData


class Market:
    def __init__(self, prices: PriceData) -> None:
        self._prices = prices

    def latest_quote(self, symbol: str) -> Quote | None:
        """The latest price for the symbol, or None if the provider has none."""
        return self._prices.latest_price(symbol)
