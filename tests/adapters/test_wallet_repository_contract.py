"""Contract every WalletRepository adapter must meet, run against each one."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.domain.wallet import Currency, Trade, Wallet
from shadowfolio.ports.wallet_repository import WalletRepository

RepositoryFactory = Callable[[], WalletRepository]

T1 = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
T2 = datetime(2026, 3, 3, 15, 0, tzinfo=UTC)


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    """Returns a factory; calling it twice gives two handles on the same storage."""
    if request.param == "in_memory":
        repository = InMemoryWalletRepository()
        return lambda: repository
    return lambda: SqliteWalletRepository(tmp_path / "data" / "test.db")


def a_wallet() -> Wallet:
    wallet = Wallet(id=uuid4(), owner_id="owner-1", name="Long term", currency=Currency.EUR)
    return wallet.deposit(uuid4(), Decimal("1000.50"), T1)


def test_added_wallet_can_be_read_back(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)

    # A second handle on the same storage: for SQLite this proves it was written to disk.
    assert make_repository().get(wallet.id) == wallet


def test_update_stores_new_operations(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)
    nvda = Trade("NVDA", Decimal("8"), Decimal("121.81"), Currency.USD)
    updated = (
        wallet.deposit(uuid4(), Decimal("10"), T2)
        .withdraw(uuid4(), Decimal("5"), T2)
        .buy(uuid4(), nvda, T1, settled_amount=Decimal("907.68"), fees=Decimal("2.00"))
    )
    make_repository().update(updated)

    assert make_repository().get(wallet.id) == updated


def test_list_by_owner_returns_only_their_wallets_in_order(
    make_repository: RepositoryFactory,
) -> None:
    first, second, other = a_wallet(), a_wallet(), replace(a_wallet(), owner_id="owner-2")
    for wallet in (first, other, second):
        make_repository().add(wallet)

    assert make_repository().list_by_owner("owner-1") == [first, second]


def test_unknown_wallet_is_none(make_repository: RepositoryFactory) -> None:
    assert make_repository().get(uuid4()) is None
