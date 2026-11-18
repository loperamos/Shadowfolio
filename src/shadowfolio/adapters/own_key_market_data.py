"""Each user's market data, fetched with their own key: what one key fetches is only ever shown to its owner.

A user's providers are built from their saved key the first time they are needed, and again only when the key changes
(replaced in Settings). Those allowed to (admins) use the server's own providers when they have saved no key; anyone
else without a key gets none, and is told to connect one.
"""

from collections.abc import Callable

from shadowfolio.domain.errors import MissingDataKeyError
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.market_data import MarketData, MarketDataSource
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository

# The provider whose key prices, corporate actions and news are fetched with.
PRICES_PROVIDER = DataProvider.ALPACA
MISSING = "connect your Alpaca key in Settings to get market data"


class OwnKeyMarketData(MarketDataSource):
    def __init__(
        self,
        keys: ProviderKeyRepository,
        build: Callable[[str, ProviderKey], MarketData],
        server: MarketData,
        uses_server_keys: Callable[[str], bool],
    ) -> None:
        """`build` makes a user's providers with their key (its user id, e.g. to keep their cache apart); `server` are
        the server's own providers, for the users `uses_server_keys` says may use them."""
        self._keys = keys
        self._build = build
        self._server = server
        self._uses_server_keys = uses_server_keys
        self._built: dict[str, tuple[tuple[str | None, str], MarketData]] = {}  # per user: the key it was built with

    def for_user(self, user_id: str) -> MarketData:
        key = self._keys.get(user_id, PRICES_PROVIDER)
        if key is None:
            if self._uses_server_keys(user_id):
                return self._server
            raise MissingDataKeyError(MISSING)
        parts = (key.key_id, key.secret)
        built = self._built.get(user_id)
        if built is None or built[0] != parts:
            built = (parts, self._build(user_id, key))
            self._built[user_id] = built
        return built[1]
