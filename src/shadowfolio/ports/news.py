"""News about listed companies."""

from abc import ABC, abstractmethod

from shadowfolio.domain.news import Article


class NewsUnavailableError(Exception):
    """The provider could not be reached or answered with an error."""


class News(ABC):
    @abstractmethod
    def latest(self, symbol: str, limit: int) -> list[Article]:
        """Up to `limit` of the latest articles about the symbol, newest first; empty when there are none.

        Raises NewsUnavailableError when the provider cannot answer.
        """
