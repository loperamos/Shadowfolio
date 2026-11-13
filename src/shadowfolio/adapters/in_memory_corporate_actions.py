"""CorporateActions holding events in memory, for tests."""

from datetime import date

from shadowfolio.domain.corporate_actions import SplitEvent
from shadowfolio.ports.corporate_actions import CorporateActions


class InMemoryCorporateActions(CorporateActions):
    def __init__(self, *splits: SplitEvent) -> None:
        self._splits = list(splits)

    def add_split(self, split: SplitEvent) -> None:
        self._splits.append(split)

    def splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        found = [s for s in self._splits if s.symbol == symbol and start <= s.ex_date <= end]
        return sorted(found, key=lambda s: s.ex_date)
