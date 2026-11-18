"""OwnKeyMarketData picks each user's market data: built with their own keys when they saved them (once, until a key
changes), the server's for those who may use it, and otherwise none, saying a key is needed. The earnings calendar
comes from their own Finnhub key, or the server's for those who may use it, or none (the key is optional)."""

from datetime import UTC, datetime

import pytest

from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_earnings_calendar import InMemoryEarningsCalendar
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_provider_key_repository import InMemoryProviderKeyRepository
from shadowfolio.adapters.own_key_market_data import OwnKeyMarketData
from shadowfolio.domain.errors import MissingDataKeyError
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.market_data import MarketData

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
SERVER = MarketData(InMemoryPriceData(), InMemoryCorporateActions(), InMemoryNews(), InMemoryEarningsCalendar())


class Built:
    """Builds market data per key, remembering what it built for whom."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, user_id: str, key: ProviderKey) -> MarketData:
        self.calls.append((user_id, key.secret))
        return MarketData(InMemoryPriceData(), InMemoryCorporateActions(), InMemoryNews())


def calendar(key: ProviderKey) -> EarningsCalendar:
    return InMemoryEarningsCalendar()


def source(keys: InMemoryProviderKeyRepository, built: Built) -> OwnKeyMarketData:
    return OwnKeyMarketData(keys, built, calendar, SERVER, uses_server_keys=lambda user_id: user_id == "admin")


def alpaca(owner: str, secret: str) -> ProviderKey:
    return ProviderKey(owner, DataProvider.ALPACA, "PKID", secret, NOW)


def test_a_users_own_key_is_used_and_built_once_until_it_changes() -> None:
    keys, built = InMemoryProviderKeyRepository(), Built()
    keys.save(alpaca("ana", "first"))
    market = source(keys, built)

    first = market.for_user("ana")
    assert market.for_user("ana") is first
    keys.save(alpaca("ana", "second"))
    assert market.for_user("ana") is not first
    assert built.calls == [("ana", "first"), ("ana", "second")]


def test_an_admin_without_a_key_uses_the_servers_and_with_one_their_own() -> None:
    keys, built = InMemoryProviderKeyRepository(), Built()
    market = source(keys, built)

    assert market.for_user("admin") is SERVER
    keys.save(alpaca("admin", "own"))
    assert market.for_user("admin") is not SERVER


def test_anyone_else_without_a_key_is_told_to_connect_one() -> None:
    with pytest.raises(MissingDataKeyError, match="connect your Alpaca key in Settings"):
        source(InMemoryProviderKeyRepository(), Built()).for_user("ben")


def test_the_earnings_calendar_comes_from_the_users_finnhub_key_or_none_without_one() -> None:
    keys = InMemoryProviderKeyRepository()
    keys.save(alpaca("ana", "alpaca-secret"))
    market = source(keys, Built())

    assert market.for_user("ana").earnings_calendar is None
    keys.save(ProviderKey("ana", DataProvider.FINNHUB, None, "finnhub-key", NOW))
    assert market.for_user("ana").earnings_calendar not in (None, SERVER.earnings_calendar)
    assert market.for_user("admin").earnings_calendar is SERVER.earnings_calendar
