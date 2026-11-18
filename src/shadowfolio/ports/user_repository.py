"""Persistence for users."""

from abc import ABC, abstractmethod

from shadowfolio.domain.users import User


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> None: ...

    @abstractmethod
    def update(self, user: User) -> None:
        """Store the user's current state (e.g. a new tier)."""

    @abstractmethod
    def get(self, user_id: str) -> User | None: ...

    @abstractmethod
    def list(self) -> list[User]:
        """Every user, in the order they were added."""
