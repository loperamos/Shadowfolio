"""Market use cases: reading market information."""

from shadowfolio.domain.errors import PriceUnavailableError
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError


class Market:
    def __init__(self, prices: PriceData) -> None:
        self._prices = prices

    def latest_quote(self, symbol: str) -> Quote | None:
        """The latest price for the symbol, or None if the provider has none."""
        try:
            return self._prices.latest_price(symbol)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
