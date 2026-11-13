"""Contract every PriceData adapter must meet.

Runs against the in-memory fake by default. Real providers run only with `pytest -m live`, using
the credentials in .env, so they never touch the network in the normal suite. Any provider we
switch to (e.g. Marketdata.app) must pass this same contract.
"""

import os
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.alpaca_price_data import AlpacaConfig, AlpacaPriceData
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData

KNOWN_SYMBOL = "NVDA"
UNKNOWN_SYMBOL = "ZZZZZZZZ"


# A minute the market was open.
TRADING_MINUTE = datetime(2024, 6, 24, 14, 26, tzinfo=UTC)
# A Sunday, whose last close is Friday's.
SUNDAY = date(2024, 6, 30)
FRIDAY = date(2024, 6, 28)


def _in_memory() -> PriceData:
    prices = InMemoryPriceData(
        {KNOWN_SYMBOL: Quote(Decimal("135.50"), Currency.USD, datetime(2026, 3, 2, 21, 0, tzinfo=UTC), Decimal("133.04"))}
    )
    prices.add_bar(KNOWN_SYMBOL, Quote(Decimal("122.005"), Currency.USD, TRADING_MINUTE))
    prices.add_close(KNOWN_SYMBOL, Quote(Decimal("123.54"), Currency.USD, datetime(2024, 6, 28, 4, 0, tzinfo=UTC)))
    return prices


def _alpaca() -> PriceData:
    load_dotenv()
    key_id, secret_key = os.environ.get("ALPACA_API_KEY_ID"), os.environ.get("ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        pytest.skip("Alpaca credentials are not set")
    return AlpacaPriceData(AlpacaConfig(key_id=key_id, secret_key=secret_key))


ADAPTERS: dict[str, Callable[[], PriceData]] = {"in_memory": _in_memory, "alpaca": _alpaca}


@pytest.fixture(params=["in_memory", pytest.param("alpaca", marks=pytest.mark.live)])
def prices(request: pytest.FixtureRequest) -> PriceData:
    return ADAPTERS[request.param]()


def test_known_symbol_has_a_usable_quote(prices: PriceData) -> None:
    quote = prices.latest_price(KNOWN_SYMBOL)

    assert quote is not None
    assert isinstance(quote.price, Decimal)
    assert quote.price > 0
    assert quote.currency is Currency.USD
    assert quote.as_of.utcoffset() is not None
    assert isinstance(quote.previous_close, Decimal)
    assert quote.previous_close > 0


def test_unknown_symbol_has_no_price(prices: PriceData) -> None:
    assert prices.latest_price(UNKNOWN_SYMBOL) is None


def test_historical_price_is_at_or_after_the_requested_time(prices: PriceData) -> None:
    quote = prices.price_at(KNOWN_SYMBOL, TRADING_MINUTE)

    assert quote is not None
    assert quote.as_of >= TRADING_MINUTE
    assert isinstance(quote.price, Decimal)
    assert quote.price > 0
    assert quote.currency is Currency.USD


def test_unknown_symbol_has_no_historical_price(prices: PriceData) -> None:
    assert prices.price_at(UNKNOWN_SYMBOL, TRADING_MINUTE) is None


def test_close_on_a_closed_day_is_the_last_trading_days(prices: PriceData) -> None:
    quote = prices.close_on(KNOWN_SYMBOL, SUNDAY)

    assert quote is not None
    assert quote.as_of.date() == FRIDAY
    assert isinstance(quote.price, Decimal)
    assert quote.price > 0
    assert quote.currency is Currency.USD


def test_unknown_symbol_has_no_close(prices: PriceData) -> None:
    assert prices.close_on(UNKNOWN_SYMBOL, SUNDAY) is None


def test_closes_between_give_each_day_its_last_close(prices: PriceData) -> None:
    closes = prices.closes_between(KNOWN_SYMBOL, FRIDAY, SUNDAY)

    assert sorted(closes) == [FRIDAY, date(2024, 6, 29), SUNDAY]
    assert {close.as_of.date() for close in closes.values()} == {FRIDAY}
    assert closes[SUNDAY] == prices.close_on(KNOWN_SYMBOL, SUNDAY)


def test_unknown_symbol_has_no_closes(prices: PriceData) -> None:
    assert prices.closes_between(UNKNOWN_SYMBOL, FRIDAY, SUNDAY) == {}
