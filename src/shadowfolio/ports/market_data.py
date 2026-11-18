"""Market data per user: what one user's work is fetched with. Each user brings their own provider key, and what a key
fetches is only ever shown to its owner, so every use case asks for the market data of the user the work is for: a
wallet's owner, or whoever is looking (the signed-in user, or an agent's token's owner)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from shadowfolio.ports.corporate_actions import CorporateActions
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.news import News
from shadowfolio.ports.price_data import PriceData


@dataclass(frozen=True)
class MarketData:
    """The providers one user's market data comes from."""

    prices: PriceData
    corporate_actions: CorporateActions
    news: News
    earnings_calendar: EarningsCalendar | None = None  # None when the user has no key for it (it is optional)


class MarketDataSource(ABC):
    @abstractmethod
    def for_user(self, user_id: str) -> MarketData:
        """The market data to fetch with for the user. Raises MissingDataKeyError when they have no key to fetch with."""
