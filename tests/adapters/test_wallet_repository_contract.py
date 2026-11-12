"""Contract every WalletRepository adapter must meet, run against each one."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.domain.wallet import Currency, Wallet
from shadowfolio.ports.wallet_repository import WalletRepository

RepositoryFactory = Callable[[], WalletRepository]


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    """Returns a factory; calling it twice gives two handles on the same storage."""
    if request.param == "in_memory":
        repository = InMemoryWalletRepository()
        return lambda: repository
    return lambda: SqliteWalletRepository(tmp_path / "data" / "test.db")


def a_wallet() -> Wallet:
    return Wallet(
        id=uuid4(),
        owner_id="owner-1",
        name="Long term",
        currency=Currency.EUR,
        cash=Decimal("1000.50"),
    )


def test_added_wallet_can_be_read_back(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)

    # A second handle on the same storage: for SQLite this proves it was written to disk.
    assert make_repository().get(wallet.id) == wallet


def test_updated_wallet_replaces_the_stored_one(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)
    updated = wallet.deposit(Decimal("10"))
    make_repository().update(updated)

    assert make_repository().get(wallet.id) == updated


def test_unknown_wallet_is_none(make_repository: RepositoryFactory) -> None:
    assert make_repository().get(uuid4()) is None
