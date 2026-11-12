"""The current time. The core never reads the system clock directly."""

from abc import ABC, abstractmethod
from datetime import datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """The current time, timezone-aware."""
