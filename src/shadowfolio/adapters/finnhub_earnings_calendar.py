"""EarningsCalendar from Finnhub's earnings calendar (https://finnhub.io/docs/api/earnings-calendar).

Its free tier needs an API key, from the configuration; nothing is asked without one. The key goes in a request header,
never in the URL, so it is not written to logs. Development only until Finnhub's terms for showing its data to other
users are confirmed (see SPEC.md). Answers are kept in memory for FRESH_FOR: earnings dates change rarely.
"""

import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx2

from shadowfolio.domain.earnings import EarningsDate, EarningsTime
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.earnings_calendar import EarningsCalendar, EarningsCalendarUnavailableError

BASE_URL = "https://finnhub.io"
CALENDAR_PATH = "/api/v1/calendar/earnings"
KEY_HEADER = "X-Finnhub-Token"
KEY_SETTING = "FINNHUB_API_KEY"
TIMEOUT_SECONDS = 10.0
FRESH_FOR = timedelta(days=1)
# When in the day results come out, as Finnhub writes it: before the open, during market hours, after the close.
TIMES = {"bmo": EarningsTime.BEFORE_OPEN, "dmh": EarningsTime.DURING_MARKET, "amc": EarningsTime.AFTER_CLOSE}


class FinnhubEarningsCalendar(EarningsCalendar):
    def __init__(self, key: str | None, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """Without `key`, nothing is asked. `transport` replaces the network in tests."""
        self._key = key
        self._clock = clock
        self._client = httpx2.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS, transport=transport, headers={KEY_HEADER: key or ""})
        self._kept: dict[tuple[str, date, date], tuple[datetime, list[EarningsDate]]] = {}

    def earnings(self, symbol: str, start: date, end: date) -> list[EarningsDate]:
        if not self._key:
            raise EarningsCalendarUnavailableError(f"Finnhub needs an API key: set {KEY_SETTING} in .env")
        now = self._clock.now()
        kept = self._kept.get((symbol, start, end))
        if kept is not None and now - kept[0] < FRESH_FOR:
            return kept[1]
        try:
            response = self._client.get(CALENDAR_PATH, params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()})
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise EarningsCalendarUnavailableError(f"Finnhub: {error}") from error
        found = sorted((_date(item) for item in json.loads(response.text).get("earningsCalendar") or []), key=lambda d: d.day)
        self._kept[(symbol, start, end)] = (now, found)
        return found


def _date(item: dict[str, Any]) -> EarningsDate:
    return EarningsDate(item["symbol"], date.fromisoformat(item["date"]), TIMES.get(item.get("hour") or "", EarningsTime.UNKNOWN))
