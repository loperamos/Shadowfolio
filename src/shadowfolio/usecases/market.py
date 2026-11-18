"""Market use cases: reading market information."""

from datetime import date, timedelta

from shadowfolio.domain.errors import CorporateActionsUnavailableNowError, PriceUnavailableError
from shadowfolio.domain.price_history import split_adjusted
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.corporate_actions import CorporateActionsUnavailableError
from shadowfolio.ports.market_data import MarketDataSource
from shadowfolio.ports.price_data import PriceDataUnavailableError

# How far back a symbol's closes go when no start is given.
DEFAULT_HISTORY = timedelta(days=10 * 365)


class Market:
    def __init__(self, market_data: MarketDataSource, clock: Clock) -> None:
        self._market_data = market_data
        self._clock = clock

    def latest_quote(self, user_id: str, symbol: str) -> Quote | None:
        """The latest price for the symbol, with the user's market data, or None if the provider has none."""
        try:
            return self._market_data.for_user(user_id).prices.latest_price(symbol)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error

    def closes(self, user_id: str, symbol: str, start: date | None = None, end: date | None = None) -> list[Quote]:
        """With the user's market data, the symbol's close on each trading day from `start` (default: `DEFAULT_HISTORY`
        before `end`) to `end` (default: today), oldest first, adjusted for splits since (in today's shares); empty when
        market data has none."""
        today = self._clock.now().date()
        end = end or today
        start = start or end - DEFAULT_HISTORY
        data = self._market_data.for_user(user_id)
        try:
            by_day = data.prices.closes_between(symbol, start, end)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        try:
            splits = data.corporate_actions.splits(symbol, start, today)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not fetch {symbol}'s splits right now; try again later") from error
        # Days without trading carry the last close: keep each trading day's own.
        return split_adjusted([close for day, close in sorted(by_day.items()) if close.as_of.date() == day], splits)
