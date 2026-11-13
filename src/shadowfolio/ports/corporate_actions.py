"""Corporate actions: splits now, dividends later."""

from abc import ABC, abstractmethod
from datetime import date

from shadowfolio.domain.corporate_actions import SplitEvent


class CorporateActionsUnavailableError(Exception):
    """The provider could not be reached or answered with an error, so nothing is known about the period asked for."""


class CorporateActions(ABC):
    @abstractmethod
    def splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        """The symbol's splits with an ex-date from `start` to `end` (both included), oldest first; empty if none.

        Raises CorporateActionsUnavailableError when the provider cannot answer.
        """
