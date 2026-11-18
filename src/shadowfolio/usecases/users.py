"""User use cases: the account made on first sign-in, and admins listing users and setting their tiers."""

from collections.abc import Collection

from shadowfolio.domain.users import Tier, User
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.user_repository import UserRepository


class NotAllowedError(Exception):
    """Only admins may do this."""


class Users:
    def __init__(self, repo: UserRepository, clock: Clock, admins: Collection[str] = ()) -> None:
        """`admins` are the user ids the configuration makes admins: always, whatever tier is stored for them."""
        self._repo = repo
        self._clock = clock
        self._admins = frozenset(admins)

    def user(self, user_id: str) -> User:
        """The user, their account made the first time they are seen: on the free plan, or as an admin."""
        user = self._repo.get(user_id)
        if user is None:
            user = User(user_id, Tier.ADMIN if user_id in self._admins else Tier.FREE, self._clock.now())
            self._repo.add(user)
        return self._as_configured(user)

    def list(self, acting_id: str) -> list[User]:
        """Every user, as they first came. Raises NotAllowedError unless `acting_id` is an admin's."""
        self._require_admin(acting_id)
        return [self._as_configured(user) for user in self._repo.list()]

    def set_tier(self, acting_id: str, user_id: str, tier: Tier) -> User | None:
        """Put a user on a tier. None if they have never signed in. Raises NotAllowedError unless `acting_id` is an
        admin's."""
        self._require_admin(acting_id)
        user = self._repo.get(user_id)
        if user is None:
            return None
        updated = user.with_tier(tier)
        self._repo.update(updated)
        return self._as_configured(updated)

    def _require_admin(self, user_id: str) -> None:
        if self.user(user_id).tier is not Tier.ADMIN:
            raise NotAllowedError("only admins can do this")

    def _as_configured(self, user: User) -> User:
        return user.with_tier(Tier.ADMIN) if user.id in self._admins else user
