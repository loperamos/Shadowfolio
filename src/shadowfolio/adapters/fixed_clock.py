"""Clock that always returns the same time, for tests."""

from datetime import datetime

from shadowfolio.ports.clock import Clock


class FixedClock(Clock):
    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at
