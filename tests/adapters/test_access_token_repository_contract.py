"""What every AccessTokenRepository must do, checked against the in-memory one and SQLite."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from shadowfolio.adapters.in_memory_access_token_repository import InMemoryAccessTokenRepository
from shadowfolio.adapters.sqlite_access_token_repository import SqliteAccessTokenRepository
from shadowfolio.domain.access import AccessToken, Scope
from shadowfolio.ports.access_token_repository import AccessTokenRepository

RepositoryFactory = Callable[[], AccessTokenRepository]
NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    """Returns a factory; calling it twice gives two handles on the same storage."""
    if request.param == "in_memory":
        repository = InMemoryAccessTokenRepository()
        return lambda: repository
    return lambda: SqliteAccessTokenRepository(tmp_path / "data" / "test.db")


def a_token(owner: str = "owner") -> AccessToken:
    return AccessToken(uuid4(), owner, "Codex", Scope.READ, (uuid4(), uuid4()), uuid4().hex * 2, "sfo_abcd", NOW)  # hashes are unique


def test_tokens_round_trip_found_by_their_hash_and_change(make_repository: RepositoryFactory) -> None:
    token = a_token()
    make_repository().add(token)

    assert make_repository().find_by_hash(token.secret_hash) == token
    assert make_repository().find_by_hash("b" * 64) is None
    used = token.used_at(NOW)
    make_repository().update(used)
    assert make_repository().get(token.id) == used


def test_tokens_are_listed_by_owner_in_the_order_they_were_added(make_repository: RepositoryFactory) -> None:
    first, second, other = a_token(), a_token(), a_token("someone else")
    for token in (first, second, other):
        make_repository().add(token)

    assert make_repository().list_by_owner("owner") == [first, second]


def test_a_deleted_token_is_gone(make_repository: RepositoryFactory) -> None:
    kept, deleted = a_token(), a_token()
    for token in (kept, deleted):
        make_repository().add(token)

    make_repository().delete(deleted.id)

    assert make_repository().list_by_owner("owner") == [kept]
    assert make_repository().find_by_hash(deleted.secret_hash) is None
