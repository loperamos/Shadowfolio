"""Usage use cases: recording what users use (requests, and provider calls made for them), and admins reading it.

Counts are added up in memory and saved about once a minute, rather than written on every request; the counts of the
last minute are lost if the app stops without saving them.
"""

import threading
from datetime import date, timedelta

from shadowfolio.domain.usage import Counter, RecordUsage, UsageCount, UsageKey
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.usage_repository import UsageRepository
from shadowfolio.usecases.users import Users

# How often recorded counts are saved.
SAVE_EVERY = timedelta(minutes=1)
# The days usage is read for when no start is given: the last week, today included.
DEFAULT_DAYS_BEFORE = timedelta(days=6)


class Usage:
    def __init__(self, repo: UsageRepository, clock: Clock, users: Users) -> None:
        self._repo = repo
        self._clock = clock
        self._users = users
        self._lock = threading.Lock()  # requests are served on several threads
        self._pending: dict[UsageKey, int] = {}
        self._saved_at = clock.now()

    def record(self, user_id: str, source: str, counter: Counter, n: int = 1) -> None:
        """Count `n` of `counter` today, for the user and source."""
        now = self._clock.now()
        key = UsageKey(now.date(), user_id, source, counter)
        with self._lock:
            self._pending[key] = self._pending.get(key, 0) + n
        if now - self._saved_at >= SAVE_EVERY:
            self.save()

    def recorder(self, user_id: str, source: str) -> RecordUsage:
        """What records counts for the user and source, e.g. for a provider's adapter built for them."""
        return lambda counter, n: self.record(user_id, source, counter, n)

    def save(self) -> None:
        """Save the counts recorded since the last save."""
        with self._lock:
            pending, self._pending = self._pending, {}
            self._saved_at = self._clock.now()
        if pending:
            self._repo.add(pending)

    def forget(self, user_id: str) -> None:
        """Forget every count of the user, saved or not (with their account)."""
        with self._lock:
            self._pending = {key: count for key, count in self._pending.items() if key.user_id != user_id}
        self._repo.delete_user(user_id)

    def report(self, acting_id: str, start: date | None = None, end: date | None = None) -> list[UsageCount]:
        """Every count from `start` (default: a week before `end`) to `end` (default: today), saved first. Raises
        NotAllowedError unless `acting_id` is an admin's."""
        self._users.require_admin(acting_id)
        self.save()
        end = end or self._clock.now().date()
        return self._repo.between(start or end - DEFAULT_DAYS_BEFORE, end)
