"""How the Finnhub earnings calendar talks HTTP, with the network replaced by a fake transport.

The fake answer follows Finnhub's earnings calendar API, trimmed to the fields the adapter reads; the live contract
test checks the real one.
"""

import json
from datetime import UTC, date, datetime

import httpx2
import pytest

from shadowfolio.adapters.finnhub_earnings_calendar import FRESH_FOR, FinnhubEarningsCalendar
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.domain.earnings import EarningsDate, EarningsTime
from shadowfolio.ports.earnings_calendar import EarningsCalendarUnavailableError

KEY = "test-key"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
CALENDAR = {
    "earningsCalendar": [
        {"date": "2027-01-28", "hour": "amc", "symbol": "AAPL", "epsEstimate": 2.67, "quarter": 1, "year": 2027},
        {"date": "2026-10-30", "hour": "bmo", "symbol": "AAPL", "epsEstimate": 1.77, "quarter": 4, "year": 2026},
        {"date": "2027-04-30", "hour": "", "symbol": "AAPL", "epsEstimate": None, "quarter": 2, "year": 2027},
    ]
}


def finnhub(
    seen: list[httpx2.Request], status: int = 200, key: str | None = KEY, clock: FixedClock | None = None
) -> FinnhubEarningsCalendar:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, text=json.dumps(CALENDAR) if status == 200 else "error")

    return FinnhubEarningsCalendar(key, clock or FixedClock(NOW), transport=httpx2.MockTransport(handler))


def test_earnings_dates_come_oldest_first_with_when_in_the_day() -> None:
    seen: list[httpx2.Request] = []

    found = finnhub(seen).earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))

    assert found == [
        EarningsDate("AAPL", date(2026, 10, 30), EarningsTime.BEFORE_OPEN),
        EarningsDate("AAPL", date(2027, 1, 28), EarningsTime.AFTER_CLOSE),
        EarningsDate("AAPL", date(2027, 4, 30), EarningsTime.UNKNOWN),
    ]
    request = seen[0]
    assert (request.url.path, dict(request.url.params)) == (
        "/api/v1/calendar/earnings",
        {"symbol": "AAPL", "from": "2026-10-01", "to": "2027-05-01"},
    )
    # The key goes in a header, never in the URL, so it is not written to logs.
    assert request.headers["X-Finnhub-Token"] == KEY and KEY not in str(request.url)


def test_answers_are_kept_for_a_while() -> None:
    seen: list[httpx2.Request] = []
    clock = FixedClock(NOW)
    calendar = finnhub(seen, clock=clock)

    calendar.earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))
    calendar.earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))
    assert len(seen) == 1
    clock.set(NOW + FRESH_FOR)
    calendar.earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))
    assert len(seen) == 2


@pytest.mark.parametrize("status", [401, 429, 503])
def test_an_error_from_finnhub_means_unavailable(status: int) -> None:
    with pytest.raises(EarningsCalendarUnavailableError):
        finnhub([], status=status).earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))


def test_without_a_key_nothing_is_asked() -> None:
    seen: list[httpx2.Request] = []

    with pytest.raises(EarningsCalendarUnavailableError, match="FINNHUB_API_KEY"):
        finnhub(seen, key=None).earnings("AAPL", date(2026, 10, 1), date(2027, 5, 1))
    assert seen == []
