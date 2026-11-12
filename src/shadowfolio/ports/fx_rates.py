"""Exchange rates."""

from abc import ABC, abstractmethod

from shadowfolio.domain.money import Currency, FxRate


class FxRates(ABC):
    @abstractmethod
    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        """The most recent rate from `base` into `quote` (two different currencies), or None if there is none."""
