"""Market prices."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from shadowfolio.domain.market import MinuteBar
from shadowfolio.domain.valuation import Quote


class PriceDataUnavailableError(Exception):
    """The provider could not be reached or answered with an error, so nothing is known about the price asked for."""


class PriceData(ABC):
    @abstractmethod
    def latest_price(self, symbol: str) -> Quote | None:
        """The most recent price for the symbol, or None if there is none.

        Raises PriceDataUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        """The first traded price at or after `at` (the open of that minute's bar), with that bar's time as `as_of`.

        Never a price from before `at`. Outside market hours this is the next open. None if there is no such price.
        Raises PriceDataUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def minute_bars(self, symbol: str, start: datetime, end: datetime) -> list[MinuteBar]:
        """The one-minute bars starting from `start` to `end` (both included), oldest first, as traded then. Empty
        for an unknown symbol. Raises PriceDataUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def close_on(self, symbol: str, day: date) -> Quote | None:
        """The closing price of the last trading day on or before `day`, as traded then (not adjusted for later splits).

        `as_of` is that trading day's start in the exchange's time zone. None if the symbol has no close in the days
        before `day` (unknown, not yet listed, or delisted). Raises PriceDataUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        """For each calendar day from `start` to `end`, what `close_on` would answer for it, with one request.

        Days without a close are left out. Raises PriceDataUnavailableError when the provider cannot answer.
        """
