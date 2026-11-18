"""PriceData from Alpaca's market-data API (free plan, IEX feed).

Development use only: Alpaca's license does not allow showing its data to public users, so this
adapter must never be wired into production.
"""

import json
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx2

from shadowfolio.adapters.daily import last_on_or_before
from shadowfolio.domain.market import MinuteBar
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError

BASE_URL = "https://data.alpaca.markets"
# The headers a key is sent in.
KEY_ID_HEADER, SECRET_KEY_HEADER = "APCA-API-KEY-ID", "APCA-API-SECRET-KEY"
# The free plan only includes the IEX exchange's feed.
FEED = "iex"
# Daily bars come from the consolidated feed (every US exchange): official closes, and whole volumes rather than one
# exchange's share. The free plan allows it for data older than SIP_DELAY; the latest prices stay on IEX.
DAILY_FEED = "sip"
SIP_DELAY = timedelta(minutes=15)
TIMEOUT_SECONDS = 10.0
# How far after a requested time to look for the next traded price (covers nights, weekends and holidays).
BAR_LOOKAHEAD = timedelta(days=7)
# How far before a requested day to look for the last close (covers weekends and holiday runs).
CLOSE_LOOKBACK = timedelta(days=10)
# Most bars Alpaca returns per page; longer ranges come in several pages.
PAGE_LIMIT = 10_000
# Alpaca answers these for symbols it does not know.
_UNKNOWN_SYMBOL_STATUSES = {HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY}
# ...and this for a symbol it cannot read (e.g. 9MD.XGAT), with this message.
INVALID_SYMBOL_MESSAGE = "invalid symbol"


@dataclass(frozen=True)
class AlpacaConfig:
    key_id: str
    secret_key: str


class AlpacaPriceData(PriceData):
    def __init__(self, config: AlpacaConfig, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """`clock` keeps daily bars clear of the consolidated feed's latest minutes; `transport` replaces the network
        in tests."""
        self._clock = clock
        self._client = httpx2.Client(
            base_url=BASE_URL,
            headers={KEY_ID_HEADER: config.key_id, SECRET_KEY_HEADER: config.secret_key},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def latest_price(self, symbol: str) -> Quote | None:
        try:
            return self._latest_price(symbol)
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error

    def latest_prices(self, symbols: Collection[str]) -> dict[str, Quote]:
        """In one request; if Alpaca refuses a symbol it cannot read, each one is asked for on its own."""
        if not symbols:
            return {}
        try:
            response = self._client.get("/v2/stocks/snapshots", params={"symbols": ",".join(symbols), "feed": FEED})
            if _unknown_symbol(response):
                return super().latest_prices(symbols)
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error
        snapshots = json.loads(response.text, parse_float=Decimal)
        quotes = {symbol: _quote(snapshot) for symbol, snapshot in snapshots.items() if snapshot}
        return {symbol: quote for symbol, quote in quotes.items() if quote is not None}

    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        try:
            return self._price_at(symbol, at)
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error

    def minute_bars(self, symbol: str, start: datetime, end: datetime) -> list[MinuteBar]:
        try:
            return self._minute_bars(symbol, start, end)
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error

    def close_on(self, symbol: str, day: date) -> Quote | None:
        try:
            return self._close_on(symbol, day)
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error

    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        try:
            return self._closes_between(symbol, start, end)
        except httpx2.HTTPError as error:
            raise PriceDataUnavailableError(f"Alpaca: {error}") from error

    def _daily_end(self, day: date) -> datetime:
        """The end of `day`, or earlier for today: never within the consolidated feed's latest minutes."""
        return min(datetime.combine(day, time.max, tzinfo=UTC), self._clock.now() - SIP_DELAY)

    def _latest_price(self, symbol: str) -> Quote | None:
        """The last trade's price and the previous day's close. Alpaca only covers US listings, so prices are in USD."""
        response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/snapshot", params={"feed": FEED})
        if _unknown_symbol(response):
            return None
        response.raise_for_status()
        # Parse numbers as Decimal directly, never through float.
        return _quote(json.loads(response.text, parse_float=Decimal))

    def _price_at(self, symbol: str, at: datetime) -> Quote | None:
        """The open of the first one-minute bar at or after `at`. Raw prices (not adjusted for later splits), as traded then."""
        params: dict[str, str | int] = {
            "timeframe": "1Min",
            "start": _rfc3339(at),
            "end": _rfc3339(at + BAR_LOOKAHEAD),
            "limit": 1,
            "sort": "asc",
            "adjustment": "raw",
            "feed": FEED,
        }
        response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/bars", params=params)
        if _unknown_symbol(response):
            return None
        response.raise_for_status()
        # Unknown symbols also come back as 200, with no bars.
        bars = json.loads(response.text, parse_float=Decimal).get("bars") or []
        if not bars:
            return None
        return Quote(price=Decimal(bars[0]["o"]), currency=Currency.USD, as_of=datetime.fromisoformat(bars[0]["t"]))

    def _minute_bars(self, symbol: str, start: datetime, end: datetime) -> list[MinuteBar]:
        """Every one-minute bar from `start` to `end`, page by page. Raw prices (not adjusted for later splits)."""
        params: dict[str, str | int] = {
            "timeframe": "1Min",
            "start": _rfc3339(start),
            "end": _rfc3339(end),
            "limit": PAGE_LIMIT,
            "sort": "asc",
            "adjustment": "raw",
            "feed": FEED,
        }
        bars: list[MinuteBar] = []
        while True:
            response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/bars", params=params)
            if _unknown_symbol(response):
                return []
            response.raise_for_status()
            page = json.loads(response.text, parse_float=Decimal)
            for bar in page.get("bars") or []:
                bars.append(
                    MinuteBar(datetime.fromisoformat(bar["t"]), Decimal(bar["o"]), Decimal(bar["h"]), Decimal(bar["l"]), Currency.USD)
                )
            token = page.get("next_page_token")
            if not token:
                return bars
            params["page_token"] = token

    def _close_on(self, symbol: str, day: date) -> Quote | None:
        """The close of the last daily bar on or before `day`. Daily bars start at midnight New York time, so every bar of
        `day` starts before the end of `day` in UTC. Raw prices, as traded then: the official close."""
        params: dict[str, str | int] = {
            "timeframe": "1Day",
            "start": _rfc3339(datetime.combine(day - CLOSE_LOOKBACK, time(), tzinfo=UTC)),
            "end": _rfc3339(self._daily_end(day)),
            "limit": 1,
            "sort": "desc",
            "adjustment": "raw",
            "feed": DAILY_FEED,
        }
        response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/bars", params=params)
        if _unknown_symbol(response):
            return None
        response.raise_for_status()
        bars = json.loads(response.text, parse_float=Decimal).get("bars") or []
        if not bars:
            return None
        return _close(bars[0])

    def _closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        """Every daily bar from `CLOSE_LOOKBACK` before `start` to the end of `end`, page by page, spread over the days."""
        params: dict[str, str | int] = {
            "timeframe": "1Day",
            "start": _rfc3339(datetime.combine(start - CLOSE_LOOKBACK, time(), tzinfo=UTC)),
            "end": _rfc3339(self._daily_end(end)),
            "limit": PAGE_LIMIT,
            "sort": "asc",
            "adjustment": "raw",
            "feed": DAILY_FEED,
        }
        closes: list[tuple[date, Quote]] = []
        while True:
            response = self._client.get(f"/v2/stocks/{quote(symbol, safe='')}/bars", params=params)
            if _unknown_symbol(response):
                return {}
            response.raise_for_status()
            page = json.loads(response.text, parse_float=Decimal)
            for bar in page.get("bars") or []:
                close = _close(bar)
                closes.append((close.as_of.date(), close))
            token = page.get("next_page_token")
            if not token:
                return last_on_or_before(closes, start, end, CLOSE_LOOKBACK)
            params["page_token"] = token


def _close(bar: dict[str, Any]) -> Quote:
    """A daily bar's close and volume."""
    volume = bar.get("v")
    return Quote(
        price=Decimal(bar["c"]),
        currency=Currency.USD,
        as_of=datetime.fromisoformat(bar["t"]),
        volume=None if volume is None else Decimal(volume),
    )


def _quote(snapshot: dict[str, Any]) -> Quote | None:
    """The last trade's price and the previous day's close, from a snapshot; None without a trade."""
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


def _unknown_symbol(response: httpx2.Response) -> bool:
    """Whether Alpaca answered that it does not know, or cannot read, the symbol: no prices, rather than an error."""
    if response.status_code in _UNKNOWN_SYMBOL_STATUSES:
        return True
    return response.status_code == HTTPStatus.BAD_REQUEST and INVALID_SYMBOL_MESSAGE in response.text


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
