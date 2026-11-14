"""Past exchange rates are kept in a SQLite file, so each is fetched from the provider once."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from shadowfolio.adapters.cached_fx_rates import CachedFxRates
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.domain.money import Currency, FxRate

FRIDAY, SUNDAY = date(2024, 6, 21), date(2024, 6, 23)
NOW = datetime(2024, 6, 25, 15, 0, tzinfo=UTC)


class CountingFxRates(InMemoryFxRates):
    """Counts the requests for rates that reach the provider."""

    requests = 0

    def rates_between(self, base: Currency, quote: Currency, start: date, end: date) -> dict[date, FxRate]:
        self.requests += 1
        return super().rates_between(base, quote, start, end)


def test_past_rates_are_fetched_once_even_after_a_restart(tmp_path: Path) -> None:
    source = CountingFxRates(FxRate(Currency.USD, Currency.EUR, Decimal("0.9356"), FRIDAY))

    path = tmp_path / "cache.sqlite"
    first = CachedFxRates(source, "ecb", path, FixedClock(NOW)).rates_between(Currency.USD, Currency.EUR, FRIDAY, SUNDAY)
    again = CachedFxRates(source, "ecb", path, FixedClock(NOW)).rate_on(Currency.USD, Currency.EUR, SUNDAY)

    assert first[SUNDAY] == again == FxRate(Currency.USD, Currency.EUR, Decimal("0.9356"), FRIDAY)
    assert source.requests == 1
