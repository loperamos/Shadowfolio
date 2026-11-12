"""Clock reading the system time, in UTC."""

from datetime import UTC, datetime

from shadowfolio.ports.clock import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
