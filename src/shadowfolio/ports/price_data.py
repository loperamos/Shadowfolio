"""Market prices."""

from abc import ABC, abstractmethod

from shadowfolio.domain.valuation import Quote


class PriceData(ABC):
    @abstractmethod
    def latest_price(self, symbol: str) -> Quote | None:
        """The most recent price for the symbol, or None if there is none."""
