"""CorporateActions holding events in memory, for tests."""

from datetime import date

from shadowfolio.domain.corporate_actions import DividendEvent, SplitEvent
from shadowfolio.ports.corporate_actions import CorporateActions


class InMemoryCorporateActions(CorporateActions):
    def __init__(self, *events: SplitEvent | DividendEvent) -> None:
        self._splits = [e for e in events if isinstance(e, SplitEvent)]
        self._dividends = [e for e in events if isinstance(e, DividendEvent)]

    def add_split(self, split: SplitEvent) -> None:
        self._splits.append(split)

    def add_dividend(self, dividend: DividendEvent) -> None:
        self._dividends.append(dividend)

    def splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        found = [s for s in self._splits if s.symbol == symbol and start <= s.ex_date <= end]
        return sorted(found, key=lambda s: s.ex_date)

    def dividends(self, symbol: str, start: date, end: date) -> list[DividendEvent]:
        found = [d for d in self._dividends if d.symbol == symbol and start <= _paid_or_ex(d) <= end]
        return sorted(found, key=_paid_or_ex)


def _paid_or_ex(dividend: DividendEvent) -> date:
    """The day the provider files the dividend under: its payment date, or its ex-date when that is unknown."""
    return dividend.payable_date or dividend.ex_date
