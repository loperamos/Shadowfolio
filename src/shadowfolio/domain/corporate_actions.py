"""Corporate actions: events decided by a company that change what shareholders hold."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SplitEvent:
    """A stock split as the market-data provider reports it: from `ex_date`, `old_rate` shares become `new_rate`."""

    symbol: str
    ex_date: date
    old_rate: Decimal
    new_rate: Decimal
    event_id: str


@dataclass(frozen=True)
class CheckedPeriod:
    """The days, from `start` to `end` (both included), for which a symbol's corporate actions have been fetched and
    applied to a wallet. Trades in the symbol are only accepted on those days, so none is ever checked against a
    holding that misses a split."""

    start: date
    end: date

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end

    def including(self, other: "CheckedPeriod") -> "CheckedPeriod":
        """This period extended to also cover `other` (the two always overlap or touch when this is used)."""
        return CheckedPeriod(min(self.start, other.start), max(self.end, other.end))
