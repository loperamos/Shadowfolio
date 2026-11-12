"""Contract every PriceData adapter must meet.

Runs against the in-memory fake by default. Real providers run only with `pytest -m live`, using
the credentials in .env, so they never touch the network in the normal suite. Any provider we
switch to (e.g. Marketdata.app) must pass this same contract.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
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


def _in_memory() -> PriceData:
    return InMemoryPriceData({KNOWN_SYMBOL: Quote(Decimal("135.50"), Currency.USD, datetime(2026, 3, 2, 21, 0, tzinfo=UTC))})


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


def test_unknown_symbol_has_no_price(prices: PriceData) -> None:
    assert prices.latest_price(UNKNOWN_SYMBOL) is None
