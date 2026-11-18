"""KeyChecker that asks each provider one small question with the key: Alpaca for SPY's latest snapshot, Finnhub for a
day of its earnings calendar. The key goes in headers, as the providers' adapters send it; what the provider answers
becomes a plain reason, never the request itself."""

from datetime import timedelta
from http import HTTPStatus

import httpx2

from shadowfolio.adapters import alpaca_price_data as alpaca
from shadowfolio.adapters import finnhub_earnings_calendar as finnhub
from shadowfolio.domain.provider_keys import NAMES, DataProvider, ProviderKey
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.key_checker import KeyChecker

# What each check asks for: a symbol every plan covers.
CHECK_SYMBOL = "SPY"
REFUSED_STATUSES = frozenset({HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN})
REFUSED = {
    DataProvider.ALPACA: "Alpaca refused this key: check that you copied both parts whole",
    DataProvider.FINNHUB: "Finnhub refused this key: check that you copied it whole",
}
LIMITED = "{name} is limiting requests with this key right now; try again in a minute"
UNREACHABLE = "could not reach {name} right now; try again later"
TIMEOUT_SECONDS = 10.0


class HttpKeyChecker(KeyChecker):
    def __init__(self, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._clock = clock
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)

    def check(self, key: ProviderKey) -> str | None:
        name = NAMES[key.provider]
        try:
            response = self._ask(key)
        except httpx2.HTTPError:
            return UNREACHABLE.format(name=name)
        if response.is_success:
            return None
        if response.status_code in REFUSED_STATUSES:
            return REFUSED[key.provider]
        if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            return LIMITED.format(name=name)
        return UNREACHABLE.format(name=name)

    def _ask(self, key: ProviderKey) -> httpx2.Response:
        match key.provider:
            case DataProvider.ALPACA:
                return self._client.get(
                    f"{alpaca.BASE_URL}/v2/stocks/snapshots",
                    params={"symbols": CHECK_SYMBOL, "feed": alpaca.FEED},
                    headers={alpaca.KEY_ID_HEADER: key.key_id or "", alpaca.SECRET_KEY_HEADER: key.secret},
                )
            case DataProvider.FINNHUB:
                today = self._clock.now().date()
                return self._client.get(
                    f"{finnhub.BASE_URL}{finnhub.CALENDAR_PATH}",
                    params={"symbol": CHECK_SYMBOL, "from": today.isoformat(), "to": (today + timedelta(days=1)).isoformat()},
                    headers={finnhub.KEY_HEADER: key.secret},
                )
