"""EarningsCalendar holding dates in memory, for tests."""

from datetime import date

from shadowfolio.domain.earnings import EarningsDate
from shadowfolio.ports.earnings_calendar import EarningsCalendar


class InMemoryEarningsCalendar(EarningsCalendar):
    def __init__(self, *dates: EarningsDate) -> None:
        self._dates = list(dates)

    def earnings(self, symbol: str, start: date, end: date) -> list[EarningsDate]:
        return sorted((d for d in self._dates if d.symbol == symbol and start <= d.day <= end), key=lambda d: d.day)
