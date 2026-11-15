"""News from Alpaca's news API (Benzinga's articles, on the free plan).

Development use only, like Alpaca's prices: its license does not allow showing its data to public users.
"""

import json
from datetime import datetime
from typing import Any

import httpx2

from shadowfolio.adapters.alpaca_price_data import BASE_URL, TIMEOUT_SECONDS, AlpacaConfig
from shadowfolio.domain.news import Article
from shadowfolio.ports.news import News, NewsUnavailableError

NEWS_PATH = "/v1beta1/news"
NEWEST_FIRST = "desc"


class AlpacaNews(News):
    def __init__(self, config: AlpacaConfig, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._client = httpx2.Client(
            base_url=BASE_URL,
            headers={"APCA-API-KEY-ID": config.key_id, "APCA-API-SECRET-KEY": config.secret_key},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def latest(self, symbol: str, limit: int) -> list[Article]:
        try:
            response = self._client.get(NEWS_PATH, params={"symbols": symbol, "limit": limit, "sort": NEWEST_FIRST})
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise NewsUnavailableError(f"Alpaca: {error}") from error
        return [_article(item) for item in json.loads(response.text).get("news") or []]


def _article(item: dict[str, Any]) -> Article:
    return Article(
        headline=item["headline"],
        summary=item.get("summary") or "",
        source=item.get("source") or "",
        url=item["url"],
        published_at=datetime.fromisoformat(item["created_at"]),
    )
