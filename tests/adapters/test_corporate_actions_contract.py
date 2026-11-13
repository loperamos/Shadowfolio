"""Contract every CorporateActions adapter must meet.

Runs against the in-memory fake by default; Alpaca runs only with `pytest -m live`.
"""

import os
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.alpaca_corporate_actions import AlpacaCorporateActions
from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.domain.corporate_actions import SplitEvent
from shadowfolio.ports.corporate_actions import CorporateActions

# NVIDIA's real 10-for-1 split.
NVDA_SPLIT_DAY = date(2024, 6, 10)
YEAR_2024 = (date(2024, 1, 1), date(2024, 12, 31))


def _in_memory() -> CorporateActions:
    return InMemoryCorporateActions(SplitEvent("NVDA", NVDA_SPLIT_DAY, Decimal(1), Decimal(10), "nvda-2024-split"))


def _alpaca() -> CorporateActions:
    load_dotenv()
    key_id, secret_key = os.environ.get("ALPACA_API_KEY_ID"), os.environ.get("ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        pytest.skip("Alpaca credentials are not set")
    return AlpacaCorporateActions(AlpacaConfig(key_id=key_id, secret_key=secret_key))


ADAPTERS: dict[str, Callable[[], CorporateActions]] = {"in_memory": _in_memory, "alpaca": _alpaca}


@pytest.fixture(params=["in_memory", pytest.param("alpaca", marks=pytest.mark.live)])
def corporate_actions(request: pytest.FixtureRequest) -> CorporateActions:
    return ADAPTERS[request.param]()


def test_a_known_split_is_reported_with_its_ratio_and_an_id(corporate_actions: CorporateActions) -> None:
    [split] = corporate_actions.splits("NVDA", *YEAR_2024)

    assert (split.symbol, split.ex_date, split.old_rate, split.new_rate) == ("NVDA", NVDA_SPLIT_DAY, Decimal(1), Decimal(10))
    assert split.event_id


def test_a_period_without_splits_is_empty(corporate_actions: CorporateActions) -> None:
    assert corporate_actions.splits("NVDA", date(2024, 7, 1), date(2024, 12, 31)) == []


def test_unknown_symbol_has_no_splits(corporate_actions: CorporateActions) -> None:
    assert corporate_actions.splits("ZZZZZZZZ", *YEAR_2024) == []
