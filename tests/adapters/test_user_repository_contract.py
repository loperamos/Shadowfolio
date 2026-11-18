"""What every UserRepository must do, checked against the in-memory one and SQLite."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shadowfolio.adapters.in_memory_user_repository import InMemoryUserRepository
from shadowfolio.adapters.sqlite_user_repository import SqliteUserRepository
from shadowfolio.domain.users import Tier, User
from shadowfolio.ports.user_repository import UserRepository

RepositoryFactory = Callable[[], UserRepository]
NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    """Returns a factory; calling it twice gives two handles on the same storage."""
    if request.param == "in_memory":
        repository = InMemoryUserRepository()
        return lambda: repository
    return lambda: SqliteUserRepository(tmp_path / "data" / "test.db")


def test_users_round_trip_and_change_tier(make_repository: RepositoryFactory) -> None:
    user = User("google-oauth2|1", Tier.FREE, NOW)
    make_repository().add(user)

    assert make_repository().get(user.id) == user
    assert make_repository().get("auth0|nobody") is None
    member = user.with_tier(Tier.MEMBER)
    make_repository().update(member)
    assert make_repository().get(user.id) == member


def test_users_are_listed_in_the_order_they_were_added(make_repository: RepositoryFactory) -> None:
    first, second = User("b", Tier.FREE, NOW), User("a", Tier.ADMIN, NOW)
    for user in (first, second):
        make_repository().add(user)

    assert make_repository().list() == [first, second]


def test_a_deleted_user_is_gone(make_repository: RepositoryFactory) -> None:
    kept, deleted = User("a", Tier.FREE, NOW), User("b", Tier.FREE, NOW)
    for user in (kept, deleted):
        make_repository().add(user)

    make_repository().delete("b")

    assert make_repository().list() == [kept]
