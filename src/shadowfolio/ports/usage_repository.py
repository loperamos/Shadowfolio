"""Persistence for usage figures: counts per day, user, source and counter, added to as they are recorded."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import date

from shadowfolio.domain.usage import UsageCount, UsageKey


class UsageRepository(ABC):
    @abstractmethod
    def add(self, counts: Mapping[UsageKey, int]) -> None:
        """Add the counts to what is stored for each key."""

    @abstractmethod
    def between(self, start: date, end: date) -> list[UsageCount]:
        """Every count from `start` to `end`, both included."""

    @abstractmethod
    def delete_user(self, user_id: str) -> None:
        """Forget every count of the user."""
