"""How the Alpaca news adapter talks HTTP, with the network replaced by a fake transport.

The fake answers follow Alpaca's news API, trimmed to the fields the adapter reads; the live contract test checks the
real one.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest

from shadowfolio.adapters.alpaca_news import AlpacaNews
from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.domain.news import Article
from shadowfolio.ports.news import NewsUnavailableError

ARTICLE = {
    "headline": "Earnings volatility watch",
    "summary": "Options price a 9% move.",
    "source": "benzinga",
    "url": "https://www.benzinga.com/63277064",
    "created_at": "2026-11-15T13:30:06Z",
    "symbols": ["NVDA", "DELL"],
}


def news_answering(body: Any, seen: list[httpx2.Request], status: int = 200) -> AlpacaNews:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, text=json.dumps(body))

    return AlpacaNews(AlpacaConfig(key_id="key", secret_key="secret"), transport=httpx2.MockTransport(handler))


def test_the_latest_articles_about_a_symbol_newest_first() -> None:
    seen: list[httpx2.Request] = []

    articles = news_answering({"news": [ARTICLE], "next_page_token": None}, seen).latest("NVDA", 10)

    assert articles == [
        Article(
            "Earnings volatility watch",
            "Options price a 9% move.",
            "benzinga",
            "https://www.benzinga.com/63277064",
            datetime(2026, 11, 15, 13, 30, 6, tzinfo=UTC),
        )
    ]
    assert dict(seen[0].url.params) == {"symbols": "NVDA", "limit": "10", "sort": "desc"}


def test_a_symbol_without_news_has_none() -> None:
    assert news_answering({"news": [], "next_page_token": None}, []).latest("ZZZZ", 10) == []


def test_an_error_from_alpaca_means_unavailable() -> None:
    with pytest.raises(NewsUnavailableError):
        news_answering({"message": "forbidden"}, [], status=403).latest("NVDA", 10)
