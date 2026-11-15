"""Market use cases: reading market information."""

from datetime import date, timedelta

from shadowfolio.domain.errors import CorporateActionsUnavailableNowError, PriceUnavailableError
from shadowfolio.domain.price_history import split_adjusted
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError

# How far back a symbol's closes go when no start is given.
DEFAULT_HISTORY = timedelta(days=10 * 365)


class Market:
    def __init__(self, prices: PriceData, clock: Clock, corporate_actions: CorporateActions) -> None:
        self._prices = prices
        self._clock = clock
        self._corporate_actions = corporate_actions

    def latest_quote(self, symbol: str) -> Quote | None:
        """The latest price for the symbol, or None if the provider has none."""
        try:
            return self._prices.latest_price(symbol)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error

    def closes(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Quote]:
        """The symbol's close on each trading day from `start` (default: `DEFAULT_HISTORY` before `end`) to `end`
        (default: today), oldest first, adjusted for splits since (in today's shares); empty when market data has none."""
        today = self._clock.now().date()
        end = end or today
        start = start or end - DEFAULT_HISTORY
        try:
            by_day = self._prices.closes_between(symbol, start, end)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        try:
            splits = self._corporate_actions.splits(symbol, start, today)
        except CorporateActionsUnavailableError as error:
            raise CorporateActionsUnavailableNowError(f"could not fetch {symbol}'s splits right now; try again later") from error
        # Days without trading carry the last close: keep each trading day's own.
        return split_adjusted([close for day, close in sorted(by_day.items()) if close.as_of.date() == day], splits)
