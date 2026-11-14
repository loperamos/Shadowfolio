"""Contract every WalletRepository adapter must meet, run against each one."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.domain.corporate_actions import CheckedPeriod, DividendEvent, RecordedDividend, SplitEvent
from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import PriceSource, Trade
from shadowfolio.domain.wallet import Wallet
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
    """An EUR wallet with a deposit, whose NVDA splits are checked from T1 to T2 (so NVDA can be traded then)."""
    wallet = Wallet(id=uuid4(), owner_id="owner-1", name="Long term", currency=Currency.EUR)
    return wallet.deposit(uuid4(), Decimal("1000.50"), T1).mark_checked("NVDA", CheckedPeriod(T1.date(), T2.date()))


def test_added_wallet_can_be_read_back(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)

    # A second handle on the same storage: for SQLite this proves it was written to disk.
    assert make_repository().get(wallet.id) == wallet


def test_update_stores_new_operations_and_name(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet()
    make_repository().add(wallet)
    nvda = Trade("NVDA", Decimal("8"), Decimal("121.81"), Currency.USD)
    updated = (
        wallet.deposit(uuid4(), Decimal("10"), T2)
        .withdraw(uuid4(), Decimal("5"), T2)
        .buy(uuid4(), nvda, T1, settled_amount=Decimal("907.68"), fees=Decimal("2.00"))
        .sell(uuid4(), nvda, T2, settled_amount=Decimal("950.00"), fees=Decimal("2.00"))
        .rename("Renamed")
    )
    make_repository().update(updated)

    assert make_repository().get(wallet.id) == updated


def test_list_by_owner_returns_only_their_wallets_in_order(make_repository: RepositoryFactory) -> None:
    first, second, other = a_wallet(), a_wallet(), replace(a_wallet(), owner_id="owner-2")
    for wallet in (first, other, second):
        make_repository().add(wallet)

    assert make_repository().list_by_owner("owner-1") == [first, second]


def test_delete_removes_the_wallet_and_its_operations(make_repository: RepositoryFactory) -> None:
    deleted, kept = a_wallet(), a_wallet()
    make_repository().add(deleted)
    make_repository().add(kept)

    make_repository().delete(deleted.id)

    assert make_repository().get(deleted.id) is None
    assert make_repository().list_by_owner("owner-1") == [kept]
    # Re-adding the same id without history must not bring the old operations back.
    empty = replace(deleted, operations=())
    make_repository().add(empty)
    assert make_repository().get(deleted.id) == empty


def test_update_stores_changed_and_removed_operations(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet().deposit(uuid4(), Decimal("10"), T2)
    make_repository().add(wallet)
    first, second = wallet.operations

    changed = wallet.deposit(first.id, Decimal("2000"), T1, replacing=first.id).remove_operation(second.id)
    make_repository().update(changed)

    assert make_repository().get(wallet.id) == changed


def test_a_market_priced_trade_keeps_its_price_source(make_repository: RepositoryFactory) -> None:
    market = Trade("NVDA", Decimal("1"), Decimal("122.005"), Currency.USD, PriceSource.MARKET)
    wallet = a_wallet().buy(uuid4(), market, T2, settled_amount=Decimal("113.99"))
    make_repository().add(wallet)

    stored = make_repository().get(wallet.id)
    assert stored == wallet
    assert stored is not None and stored.hindsight


def test_sqlite_upgrades_a_database_created_before_price_sources(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    wallet = a_wallet().buy(uuid4(), Trade("NVDA", Decimal("1"), Decimal("121.81"), Currency.USD), T2, settled_amount=Decimal("113.80"))
    SqliteWalletRepository(path).add(wallet)
    with closing(sqlite3.connect(path)) as conn, conn:  # back to the schema before the price_source column
        conn.execute("ALTER TABLE operations DROP COLUMN price_source")

    assert SqliteWalletRepository(path).get(wallet.id) == wallet


def test_a_split_round_trips(make_repository: RepositoryFactory) -> None:
    nvda = Trade("NVDA", Decimal("8"), Decimal("121.81"), Currency.USD)
    wallet = a_wallet().buy(uuid4(), nvda, T1, settled_amount=Decimal("907.68"))
    wallet = wallet.apply_split(uuid4(), SplitEvent("NVDA", T2.date(), Decimal(1), Decimal(10), "nvda-split"), T2)
    make_repository().add(wallet)

    stored = make_repository().get(wallet.id)
    assert stored == wallet
    assert stored is not None and stored.holdings == {"NVDA": Decimal("80")}


def test_dividends_round_trip(make_repository: RepositoryFactory) -> None:
    nvda = Trade("NVDA", Decimal("8"), Decimal("121.81"), Currency.USD)
    wallet = a_wallet().set_withholding_rate(Decimal("0.15")).buy(uuid4(), nvda, T1, settled_amount=Decimal("907.68"))
    event = DividendEvent("NVDA", T2.date(), T2.date(), Decimal("0.01"), Currency.USD, "nvda-dividend")
    wallet = wallet.record_dividends([RecordedDividend(event, Decimal("0.93"))])
    make_repository().add(wallet)

    stored = make_repository().get(wallet.id)
    assert stored == wallet
    assert stored is not None and [op.type for op in stored.operations][-1] == "dividend"
    assert stored.operations[-1].cash_delta == Decimal("0.06")  # 0.07 gross, less 15%


def test_dividends_without_a_payment_date_round_trip(make_repository: RepositoryFactory) -> None:
    nvda = Trade("NVDA", Decimal("8"), Decimal("121.81"), Currency.USD)
    wallet = a_wallet().buy(uuid4(), nvda, T1, settled_amount=Decimal("907.68"))
    event = DividendEvent("NVDA", T2.date(), None, Decimal("0.01"), Currency.USD, "nvda-undated")
    wallet = wallet.record_dividends([RecordedDividend(event, None)])
    make_repository().add(wallet)

    stored = make_repository().get(wallet.id)
    assert stored == wallet
    assert stored is not None and stored.uncredited_dividends == (event,)


def test_imported_dividends_round_trip(make_repository: RepositoryFactory) -> None:
    wallet = a_wallet().record_dividend(uuid4(), T2, "NVDA", "USD", Decimal("9.50"), Decimal("1.43"), Decimal("0.81"), Decimal("6.43"))
    make_repository().add(wallet)

    assert make_repository().get(wallet.id) == wallet


def test_fees_and_income_round_trip(make_repository: RepositoryFactory) -> None:
    wallet = (
        a_wallet()
        .pay_fee(uuid4(), T2, Decimal("2.50"), "Exchange connection fee 2026 (NYSE)")
        .record_income(uuid4(), T2, Decimal("-0.01"), "Interest charged")
    )
    make_repository().add(wallet)

    assert make_repository().get(wallet.id) == wallet


def test_unknown_wallet_is_none(make_repository: RepositoryFactory) -> None:
    assert make_repository().get(uuid4()) is None
