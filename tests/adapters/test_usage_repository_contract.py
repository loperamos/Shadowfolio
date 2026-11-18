"""What every UsageRepository must do, checked against the in-memory one and SQLite: counts add up per day, user,
source and counter, and are read back for a period."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from shadowfolio.adapters.in_memory_usage_repository import InMemoryUsageRepository
from shadowfolio.adapters.sqlite_usage_repository import SqliteUsageRepository
from shadowfolio.domain.usage import Counter, UsageCount, UsageKey
from shadowfolio.ports.usage_repository import UsageRepository

RepositoryFactory = Callable[[], UsageRepository]
MONDAY, TUESDAY, WEDNESDAY = date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)


@pytest.fixture(params=["in_memory", "sqlite"])
def make_repository(request: pytest.FixtureRequest, tmp_path: Path) -> RepositoryFactory:
    if request.param == "in_memory":
        repository = InMemoryUsageRepository()
        return lambda: repository
    return lambda: SqliteUsageRepository(tmp_path / "data" / "test.db")


def test_counts_add_up_and_are_read_for_a_period(make_repository: RepositoryFactory) -> None:
    calls = UsageKey(MONDAY, "ana", "alpaca", Counter.CALLS)
    errors = UsageKey(MONDAY, "ana", "alpaca", Counter.ERRORS)
    later = UsageKey(WEDNESDAY, "ben", "web", Counter.REQUESTS)
    make_repository().add({calls: 3, errors: 1})
    make_repository().add({calls: 2, later: 5})

    assert sorted(make_repository().between(MONDAY, TUESDAY), key=lambda count: count.key.counter) == [
        UsageCount(calls, 5),
        UsageCount(errors, 1),
    ]
    assert make_repository().between(TUESDAY, WEDNESDAY) == [UsageCount(later, 5)]


def test_a_users_counts_are_deleted_with_them(make_repository: RepositoryFactory) -> None:
    anas, bens = UsageKey(MONDAY, "ana", "web", Counter.REQUESTS), UsageKey(MONDAY, "ben", "web", Counter.REQUESTS)
    make_repository().add({anas: 1, bens: 2})

    make_repository().delete_user("ben")

    assert make_repository().between(MONDAY, MONDAY) == [UsageCount(anas, 1)]
