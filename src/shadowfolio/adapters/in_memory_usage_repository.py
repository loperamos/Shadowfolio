"""UsageRepository in memory, for tests."""

from collections.abc import Mapping
from datetime import date

from shadowfolio.domain.usage import UsageCount, UsageKey
from shadowfolio.ports.usage_repository import UsageRepository


class InMemoryUsageRepository(UsageRepository):
    def __init__(self) -> None:
        self._counts: dict[UsageKey, int] = {}

    def add(self, counts: Mapping[UsageKey, int]) -> None:
        for key, count in counts.items():
            self._counts[key] = self._counts.get(key, 0) + count

    def between(self, start: date, end: date) -> list[UsageCount]:
        return [UsageCount(key, count) for key, count in self._counts.items() if start <= key.day <= end]
