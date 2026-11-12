"""Wiring for tests: fakes for every port, nothing persisted."""

from datetime import UTC, datetime

from fastapi import FastAPI

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.price_data import PriceData
from shadowfolio.usecases.history import History
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets

DEFAULT_NOW = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)


def build_test_app(clock: Clock | None = None, prices: PriceData | None = None) -> FastAPI:
    """Pass fakes to control them; otherwise "now" is DEFAULT_NOW and there are no prices."""
    clock = clock or FixedClock(DEFAULT_NOW)
    prices = prices or InMemoryPriceData()
    wallet_repository = InMemoryWalletRepository()
    return create_app(
        wallets=Wallets(wallet_repository, clock),
        history=History(wallet_repository, clock),
        valuation=Valuation(wallet_repository, prices),
        market=Market(prices),
    )
