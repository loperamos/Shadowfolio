"""What every EarningsCalendar must do, checked against the fake and, with a key, Finnhub itself."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.finnhub_earnings_calendar import FinnhubEarningsCalendar
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_earnings_calendar import InMemoryEarningsCalendar
from shadowfolio.domain.earnings import EarningsDate, EarningsTime
from shadowfolio.ports.earnings_calendar import EarningsCalendar

KEY_SETTING = "FINNHUB_API_KEY"
SYMBOL = "AAPL"  # reports every quarter
TODAY = datetime.now(UTC).date()


def _finnhub() -> EarningsCalendar:
    load_dotenv()
    key = os.environ.get(KEY_SETTING)
    if not key:
        pytest.skip(f"{KEY_SETTING} is not set")
    return FinnhubEarningsCalendar(key, FixedClock(datetime.now(UTC)))


def _in_memory() -> EarningsCalendar:
    today = TODAY
    return InMemoryEarningsCalendar(
        EarningsDate(SYMBOL, today - timedelta(days=60), EarningsTime.AFTER_CLOSE),
        EarningsDate(SYMBOL, today + timedelta(days=30), EarningsTime.AFTER_CLOSE),
    )


CALENDARS: dict[str, Callable[[], EarningsCalendar]] = {"in_memory": _in_memory, "finnhub": _finnhub}


@pytest.fixture(params=["in_memory", pytest.param("finnhub", marks=pytest.mark.live)])
def calendar(request: pytest.FixtureRequest) -> EarningsCalendar:
    return CALENDARS[request.param]()


def test_a_company_reporting_every_quarter_has_dates_within_the_range_oldest_first(calendar: EarningsCalendar) -> None:
    start, end = TODAY - timedelta(days=100), TODAY + timedelta(days=100)

    found = calendar.earnings(SYMBOL, start, end)

    assert found, "a company reporting every quarter has a date within 100 days either way"
    assert all(item.symbol == SYMBOL and start <= item.day <= end for item in found)
    assert [item.day for item in found] == sorted(item.day for item in found)


def test_an_unknown_symbol_has_no_dates(calendar: EarningsCalendar) -> None:
    assert calendar.earnings("ZZZZZZZZ", TODAY, TODAY + timedelta(days=100)) == []
