"""Contract every FxRates adapter must meet.

Runs against the in-memory fake by default; the ECB runs only with `pytest -m live`.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from shadowfolio.adapters.cached_fx_rates import CachedFxRates
from shadowfolio.adapters.ecb_fx_rates import EcbFxRates
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRates

# 23 June 2024 is a Sunday: no rate is published; the Friday before (21 June) applies.
SUNDAY = date(2024, 6, 23)
FRIDAY = date(2024, 6, 21)


def _in_memory() -> FxRates:
    day = date(2026, 11, 12)
    return InMemoryFxRates(
        FxRate(Currency.EUR, Currency.USD, Decimal("1.1081"), day),
        FxRate(Currency.USD, Currency.EUR, Decimal(1) / Decimal("1.1081"), day),
        FxRate(Currency.EUR, Currency.USD, Decimal("1.0688"), FRIDAY),
    )


def _cached(cache_dir: Path) -> FxRates:
    """The cache in front of the fake."""
    return CachedFxRates(_in_memory(), "in_memory", cache_dir / "cache.sqlite", FixedClock(datetime(2026, 11, 13, tzinfo=UTC)))


ADAPTERS: dict[str, Callable[[Path], FxRates]] = {
    "in_memory": lambda _: _in_memory(),
    "cached": _cached,
    "ecb": lambda _: EcbFxRates(SystemClock()),
}


@pytest.fixture(params=["in_memory", "cached", pytest.param("ecb", marks=pytest.mark.live)])
def fx_rates(request: pytest.FixtureRequest, tmp_path: Path) -> FxRates:
    return ADAPTERS[request.param](tmp_path)


def test_rate_between_supported_currencies(fx_rates: FxRates) -> None:
    rate = fx_rates.latest_rate(Currency.EUR, Currency.USD)

    assert rate is not None
    assert (rate.base, rate.quote) == (Currency.EUR, Currency.USD)
    assert isinstance(rate.rate, Decimal)
    assert rate.rate > 0
    assert isinstance(rate.as_of, date)


def test_opposite_rates_are_inverses(fx_rates: FxRates) -> None:
    there, back = fx_rates.latest_rate(Currency.EUR, Currency.USD), fx_rates.latest_rate(Currency.USD, Currency.EUR)

    assert there is not None and back is not None
    assert abs(there.rate * back.rate - 1) < Decimal("1e-12")


def test_rate_on_a_day_without_one_is_the_last_published_before_it(fx_rates: FxRates) -> None:
    rate = fx_rates.rate_on(Currency.EUR, Currency.USD, SUNDAY)

    assert rate is not None
    assert rate.as_of == FRIDAY
    assert isinstance(rate.rate, Decimal)
    assert rate.rate > 0


def test_rates_between_give_each_day_the_last_published_rate(fx_rates: FxRates) -> None:
    saturday = date(2024, 6, 22)

    rates = fx_rates.rates_between(Currency.EUR, Currency.USD, FRIDAY, SUNDAY)

    assert sorted(rates) == [FRIDAY, saturday, SUNDAY]
    assert {rate.as_of for rate in rates.values()} == {FRIDAY}
    assert rates[SUNDAY] == fx_rates.rate_on(Currency.EUR, Currency.USD, SUNDAY)
