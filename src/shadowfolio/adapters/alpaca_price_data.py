"""PriceData from Alpaca's market-data API (free plan, IEX feed).

Development use only: Alpaca's license does not allow showing its data to public users, so this
adapter must never be wired into production.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from urllib.parse import quote

import httpx2

from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData

BASE_URL = "https://data.alpaca.markets"
# The free plan only includes the IEX exchange's feed.
FEED = "iex"
TIMEOUT_SECONDS = 10.0
# Alpaca answers these for symbols it does not know.
_UNKNOWN_SYMBOL_STATUSES = {HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY}


@dataclass(frozen=True)
class AlpacaConfig:
    key_id: str
    secret_key: str


class AlpacaPriceData(PriceData):
    def __init__(self, config: AlpacaConfig, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._client = httpx2.Client(
            base_url=BASE_URL,
            headers={"APCA-API-KEY-ID": config.key_id, "APCA-API-SECRET-KEY": config.secret_key},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def latest_price(self, symbol: str) -> Quote | None:
        """The last trade's price and the previous day's close. Alpaca only covers US listings, so prices are in USD."""
        response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/snapshot", params={"feed": FEED})
        if response.status_code in _UNKNOWN_SYMBOL_STATUSES:
            return None
        response.raise_for_status()
        # Parse numbers as Decimal directly, never through float.
        snapshot = json.loads(response.text, parse_float=Decimal)
        trade = snapshot.get("latestTrade")
        if not trade:
            return None
        previous_bar = snapshot.get("prevDailyBar")
        return Quote(
            price=Decimal(trade["p"]),
            currency=Currency.USD,
            as_of=datetime.fromisoformat(trade["t"]),
            previous_close=Decimal(previous_bar["c"]) if previous_bar else None,
        )
