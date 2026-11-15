"""News holding articles in memory, for tests."""

from shadowfolio.domain.news import Article
from shadowfolio.ports.news import News


class InMemoryNews(News):
    def __init__(self, articles: dict[str, list[Article]] | None = None) -> None:
        self._articles = {symbol: list(found) for symbol, found in (articles or {}).items()}

    def latest(self, symbol: str, limit: int) -> list[Article]:
        return sorted(self._articles.get(symbol, []), key=lambda article: article.published_at, reverse=True)[:limit]
