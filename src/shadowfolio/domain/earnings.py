"""When companies report their results: the days prices often jump, as news about earnings comes out."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class EarningsTime(StrEnum):
    BEFORE_OPEN = "before_open"
    DURING_MARKET = "during_market"
    AFTER_CLOSE = "after_close"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EarningsDate:
    symbol: str
    day: date
    time: EarningsTime  # when in the day, as the company announced it
