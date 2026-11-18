"""Each user's market data, fetched with their own keys: what one key fetches is only ever shown to its owner.

A user's providers are built from their saved keys the first time they are needed, and again only when a key changes
(replaced in Settings). Those allowed to (admins) use the server's own providers for what they have saved no key for;
anyone else without an Alpaca key gets no market data, and is told to connect one. The Finnhub key is optional:
without it there is no earnings calendar.
"""

from collections.abc import Callable
from dataclasses import replace

from shadowfolio.domain.errors import MissingDataKeyError
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.market_data import MarketData, MarketDataSource
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository

# The providers whose keys prices, corporate actions and news, and the earnings calendar, are fetched with.
PRICES_PROVIDER, EARNINGS_PROVIDER = DataProvider.ALPACA, DataProvider.FINNHUB
MISSING = "connect your Alpaca key in Settings to get market data"

KeyParts = tuple[str | None, str] | None


class OwnKeyMarketData(MarketDataSource):
    def __init__(
        self,
        keys: ProviderKeyRepository,
        build: Callable[[str, ProviderKey], MarketData],
        build_earnings: Callable[[ProviderKey], EarningsCalendar],
        server: MarketData,
        uses_server_keys: Callable[[str], bool],
    ) -> None:
        """`build` makes a user's providers with their Alpaca key (its user id, e.g. to keep their cache apart), and
        `build_earnings` their earnings calendar with their Finnhub key; `server` are the server's own providers, for
        the users `uses_server_keys` says may use them."""
        self._keys = keys
        self._build = build
        self._build_earnings = build_earnings
        self._server = server
        self._uses_server_keys = uses_server_keys
        # Per user: the keys (and whether the server's may be used) it was built with, and what was built.
        self._built: dict[str, tuple[tuple[KeyParts, KeyParts, bool], MarketData]] = {}

    def for_user(self, user_id: str) -> MarketData:
        prices_key = self._keys.get(user_id, PRICES_PROVIDER)
        earnings_key = self._keys.get(user_id, EARNINGS_PROVIDER)
        server_allowed = self._uses_server_keys(user_id)
        if prices_key is None and not server_allowed:
            raise MissingDataKeyError(MISSING)
        built_with = (_parts(prices_key), _parts(earnings_key), server_allowed)
        built = self._built.get(user_id)
        if built is None or built[0] != built_with:
            base = self._server if prices_key is None else self._build(user_id, prices_key)
            calendar: EarningsCalendar | None = None
            if earnings_key is not None:
                calendar = self._build_earnings(earnings_key)
            elif server_allowed:
                calendar = self._server.earnings_calendar
            built = (built_with, base if calendar is base.earnings_calendar else replace(base, earnings_calendar=calendar))
            self._built[user_id] = built
        return built[1]


def _parts(key: ProviderKey | None) -> KeyParts:
    return None if key is None else (key.key_id, key.secret)
