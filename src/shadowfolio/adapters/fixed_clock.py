"""Clock that always returns the same time, for tests."""

from datetime import datetime

from shadowfolio.ports.clock import Clock


class FixedClock(Clock):
    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        """Moves "now", e.g. to the day after an event in a test."""
        self._at = at
