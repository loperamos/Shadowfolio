"""Market prices."""

from abc import ABC, abstractmethod
from datetime import datetime

from shadowfolio.domain.valuation import Quote


class PriceData(ABC):
    @abstractmethod
    def latest_price(self, symbol: str) -> Quote | None:
        """The most recent price for the symbol, or None if there is none."""

    @abstractmethod
    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        """The first traded price at or after `at` (the open of that minute's bar), with that bar's time as `as_of`.

        Never a price from before `at`. Outside market hours this is the next open. None if there is no such price.
        """
