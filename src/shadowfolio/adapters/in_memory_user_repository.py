"""UserRepository in memory, for tests."""

from shadowfolio.domain.users import User
from shadowfolio.ports.user_repository import UserRepository


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}  # in the order they were added

    def add(self, user: User) -> None:
        self._users[user.id] = user

    def update(self, user: User) -> None:
        self._users[user.id] = user

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def list(self) -> list[User]:
        return list(self._users.values())
