"""How a wallet (or a benchmark) did over a period: gain, and returns that ignore or include when money moved."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from shadowfolio.domain.performance import DayValue, cumulative_returns, performance

DAY0 = date(2024, 1, 1)


def day(offset: int, value: str | None, flow: str = "0") -> DayValue:
    """The value at the end of DAY0 + offset, money put in (or taken out) that day included."""
    return DayValue(DAY0 + timedelta(days=offset), None if value is None else Decimal(value), Decimal(flow))


def close_to(expected: str) -> object:
    return pytest.approx(Decimal(expected), abs=Decimal("0.0001"))


def test_the_time_weighted_return_ignores_money_put_in() -> None:
    # +10%, then 1000 more put in while flat, then +10% again: 1.1 x 1.1 = +21%, whatever the amounts.
    points = [day(0, "1000"), day(1, "1100"), day(2, "2100", flow="1000"), day(3, "2310")]

    result = performance(points, DAY0 + timedelta(days=1), DAY0 + timedelta(days=3))

    assert result is not None
    assert (result.start_value, result.end_value, result.net_flows, result.gain) == (
        Decimal(1000),
        Decimal(2310),
        Decimal(1000),
        Decimal(310),
    )
    assert result.time_weighted == close_to("0.21")


def test_the_money_weighted_return_is_the_yearly_rate_that_explains_the_end_value() -> None:
    # 1000 at the start grows to 1100 a year later: 10% a year, and 10% over the period.
    points = [day(0, "1000"), day(365, "1100")]

    result = performance(points, DAY0 + timedelta(days=1), DAY0 + timedelta(days=365))

    assert result is not None
    assert (result.money_weighted, result.money_weighted_per_year) == (close_to("0.10"), close_to("0.10"))


def test_returns_per_year_only_for_periods_of_a_year_or_more() -> None:
    two_years = performance([day(0, "1000"), day(730, "1210")], DAY0 + timedelta(days=1), DAY0 + timedelta(days=730))
    a_month = performance([day(0, "1000"), day(30, "1010")], DAY0 + timedelta(days=1), DAY0 + timedelta(days=30))

    assert two_years is not None and two_years.time_weighted_per_year == close_to("0.10")  # 1.21 over two years
    assert a_month is not None and (a_month.time_weighted_per_year, a_month.money_weighted_per_year) == (None, None)


def test_money_moved_on_an_unvalued_day_counts_at_the_next_valued_one() -> None:
    points = [day(0, "1000"), day(1, None, flow="500"), day(2, "1650")]

    result = performance(points, DAY0 + timedelta(days=1), DAY0 + timedelta(days=2))

    assert result is not None
    assert (result.net_flows, result.gain, result.time_weighted) == (Decimal(500), Decimal(150), close_to("0.15"))  # 1150 / 1000


def test_a_wallet_starting_empty_starts_with_its_first_deposit() -> None:
    points = [day(0, "0"), day(1, "1000", flow="1000"), day(2, "1100")]

    result = performance(points, DAY0, DAY0 + timedelta(days=2))

    assert result is not None
    assert (result.net_flows, result.gain, result.time_weighted) == (Decimal(1000), Decimal(100), close_to("0.10"))


def test_a_period_without_any_valued_day_has_no_performance() -> None:
    assert performance([day(0, None), day(1, None)], DAY0, DAY0 + timedelta(days=1)) is None


def test_cumulative_returns_start_at_zero_and_skip_unvalued_days() -> None:
    # +10%, then 1000 more put in while flat, an unvalued day, then +10% again on the whole.
    points = [day(0, "1000"), day(1, "1100"), day(2, "2100", flow="1000"), day(3, None), day(4, "2310")]

    returns = cumulative_returns(points, DAY0 + timedelta(days=1), DAY0 + timedelta(days=4))

    assert [((when - DAY0).days, value) for when, value in returns] == [
        (0, Decimal(0)),
        (1, close_to("0.10")),
        (2, close_to("0.10")),
        (3, None),
        (4, close_to("0.21")),
    ]
