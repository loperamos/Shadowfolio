"""What every ProviderKeyRepository must do, checked against the in-memory one and SQLite; and SQLite keeps the keys
encrypted, readable only with the master key it was given."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from shadowfolio.adapters.in_memory_provider_key_repository import InMemoryProviderKeyRepository
from shadowfolio.adapters.sqlite_provider_key_repository import KeysUnreadableError, SqliteProviderKeyRepository
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository

RepositoryFactory = Callable[[], ProviderKeyRepository]
NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
MASTER_KEY = Fernet.generate_key().decode()


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    """Returns a factory; calling it twice gives two handles on the same storage."""
    if request.param == "in_memory":
        repository = InMemoryProviderKeyRepository()
        return lambda: repository
    return lambda: SqliteProviderKeyRepository(tmp_path / "data" / "test.db", MASTER_KEY)


def alpaca(owner: str = "ana", key_id: str = "PKID1234", secret: str = "plain-secret-value") -> ProviderKey:
    return ProviderKey(owner, DataProvider.ALPACA, key_id, secret, NOW)


def test_keys_are_saved_per_owner_and_provider_replaced_and_deleted(make_repository: RepositoryFactory) -> None:
    first, finnhub, others = alpaca(), ProviderKey("ana", DataProvider.FINNHUB, None, "f", NOW), alpaca("ben")
    for key in (first, finnhub, others):
        make_repository().save(key)
    replaced = alpaca(key_id="PKID5678", secret="another")
    make_repository().save(replaced)

    assert make_repository().get("ana", DataProvider.ALPACA) == replaced
    assert sorted(make_repository().list_by_owner("ana"), key=lambda key: key.provider) == [replaced, finnhub]
    assert make_repository().delete("ana", DataProvider.ALPACA) is True
    assert make_repository().get("ana", DataProvider.ALPACA) is None
    assert make_repository().delete("ana", DataProvider.ALPACA) is False
    assert make_repository().get("ben", DataProvider.ALPACA) == others


def test_sqlite_keeps_keys_encrypted_and_needs_the_master_key(tmp_path: Path) -> None:
    path = tmp_path / "data" / "test.db"
    SqliteProviderKeyRepository(path, MASTER_KEY).save(alpaca())

    stored = path.read_bytes()
    assert b"plain-secret-value" not in stored
    assert b"PKID1234" not in stored
    with pytest.raises(KeysUnreadableError):
        SqliteProviderKeyRepository(path, Fernet.generate_key().decode()).get("ana", DataProvider.ALPACA)


def test_sqlite_refuses_a_master_key_that_is_not_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHADOWFOLIO_KEYS_SECRET"):
        SqliteProviderKeyRepository(tmp_path / "test.db", "not-a-key")
