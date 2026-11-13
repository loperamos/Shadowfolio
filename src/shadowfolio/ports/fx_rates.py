"""Exchange rates."""

from abc import ABC, abstractmethod
from datetime import date

from shadowfolio.domain.money import Currency, FxRate


class FxRatesUnavailableError(Exception):
    """The provider could not be reached or answered with an error, so nothing is known about the rate asked for."""


class FxRates(ABC):
    @abstractmethod
    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        """The most recent rate from `base` into `quote` (two different currencies), or None if there is none.

        Raises FxRatesUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        """The rate from `base` into `quote` on `day`, or the last one published before it (weekends, holidays).

        Raises FxRatesUnavailableError when the provider cannot answer.
        """

    @abstractmethod
    def rates_between(self, base: Currency, quote: Currency, start: date, end: date) -> dict[date, FxRate]:
        """For each calendar day from `start` to `end`, what `rate_on` would answer for it, without a request per day.

        Days without a rate are left out. Raises FxRatesUnavailableError when the provider cannot answer.
        """
