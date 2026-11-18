"""User use cases: the account made on first sign-in, and admins listing users and setting their tiers."""

from collections.abc import Collection
from datetime import datetime, timedelta

from shadowfolio.domain.users import Tier, User
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.user_repository import UserRepository

# Requests are counted per user in windows of a minute, each starting on the clock's minute.
REQUEST_WINDOW = timedelta(minutes=1)


class NotAllowedError(Exception):
    """Only admins may do this."""


class Users:
    def __init__(self, repo: UserRepository, clock: Clock, admins: Collection[str] = ()) -> None:
        """`admins` are the user ids the configuration makes admins: always, whatever tier is stored for them."""
        self._repo = repo
        self._clock = clock
        self._admins = frozenset(admins)
        # Requests made in the current window, per user: in memory, as they only matter for a minute.
        self._requests: dict[str, tuple[datetime, int]] = {}

    def user(self, user_id: str) -> User:
        """The user, their account made the first time they are seen: on the free plan, or as an admin."""
        user = self._repo.get(user_id)
        if user is None:
            user = User(user_id, Tier.ADMIN if user_id in self._admins else Tier.FREE, self._clock.now())
            self._repo.add(user)
        return self._as_configured(user)

    def count_request(self, user_id: str) -> None:
        """Count a request by the user, to the web API or the MCP server. Raises RateLimitError, counting nothing, if
        their plan allows no more in this window."""
        now = self._clock.now()
        start = now.replace(second=0, microsecond=0)
        window, made = self._requests.get(user_id, (start, 0))
        if window != start:
            made = 0
        self.user(user_id).check_request(made, start + REQUEST_WINDOW, now)
        self._requests[user_id] = (start, made + 1)

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
