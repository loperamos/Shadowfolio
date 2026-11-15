"""When listed companies report their results."""

from abc import ABC, abstractmethod
from datetime import date

from shadowfolio.domain.earnings import EarningsDate


class EarningsCalendarUnavailableError(Exception):
    """The provider could not be reached, answered with an error, or is not set up."""


class EarningsCalendar(ABC):
    @abstractmethod
    def earnings(self, symbol: str, start: date, end: date) -> list[EarningsDate]:
        """The days from `start` to `end` (both included) the symbol's company reports, or reported, results, oldest
        first; empty when there are none.

        Raises EarningsCalendarUnavailableError when the provider cannot answer.
        """
