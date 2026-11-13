"""Contract every FxRates adapter must meet.

Runs against the in-memory fake by default; the ECB runs only with `pytest -m live`.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from shadowfolio.adapters.ecb_fx_rates import EcbFxRates
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


ADAPTERS: dict[str, Callable[[], FxRates]] = {"in_memory": _in_memory, "ecb": lambda: EcbFxRates(SystemClock())}


@pytest.fixture(params=["in_memory", pytest.param("ecb", marks=pytest.mark.live)])
def fx_rates(request: pytest.FixtureRequest) -> FxRates:
    return ADAPTERS[request.param]()


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
