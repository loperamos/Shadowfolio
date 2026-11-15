"""Contract every News adapter must meet.

Runs against the in-memory fake by default; Alpaca runs only with `pytest -m live`, with the credentials in .env.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.alpaca_news import AlpacaNews
from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.domain.news import Article
from shadowfolio.ports.news import News

KNOWN_SYMBOL = "NVDA"
UNKNOWN_SYMBOL = "ZZZZZZZZ"


def _in_memory() -> News:
    articles = [
        Article(f"Headline {n}", "", "benzinga", f"https://example.com/{n}", datetime(2026, 11, n, tzinfo=UTC)) for n in range(1, 5)
    ]
    return InMemoryNews({KNOWN_SYMBOL: articles})


def _alpaca() -> News:
    load_dotenv()
    key_id, secret_key = os.environ.get("ALPACA_API_KEY_ID"), os.environ.get("ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        pytest.skip("Alpaca credentials are not set")
    return AlpacaNews(AlpacaConfig(key_id=key_id, secret_key=secret_key))


ADAPTERS: dict[str, Callable[[], News]] = {"in_memory": _in_memory, "alpaca": _alpaca}


@pytest.fixture(params=["in_memory", pytest.param("alpaca", marks=pytest.mark.live)])
def news(request: pytest.FixtureRequest) -> News:
    return ADAPTERS[request.param]()


def test_the_latest_articles_come_newest_first_up_to_the_limit(news: News) -> None:
    articles = news.latest(KNOWN_SYMBOL, 3)

    assert 0 < len(articles) <= 3
    assert [a.published_at for a in articles] == sorted((a.published_at for a in articles), reverse=True)
    assert all(a.headline and a.url.startswith("https://") and a.published_at.utcoffset() is not None for a in articles)


def test_an_unknown_symbol_has_no_news(news: News) -> None:
    assert news.latest(UNKNOWN_SYMBOL, 3) == []
