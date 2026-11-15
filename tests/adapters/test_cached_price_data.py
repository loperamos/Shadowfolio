"""Past daily closes are kept in a SQLite file, so each is fetched from the provider once."""

from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from shadowfolio.adapters.cached_price_data import LATEST_FRESH_FOR, CachedPriceData
from shadowfolio.adapters.daily_cache import FRESH_FOR
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote

SYMBOL = "NVDA"
SOURCE = "alpaca/iex"
THURSDAY, FRIDAY, SUNDAY, MONDAY, TUESDAY = date(2024, 6, 27), date(2024, 6, 28), date(2024, 6, 30), date(2024, 7, 1), date(2024, 7, 2)
NOW = datetime(2024, 7, 2, 15, 0, tzinfo=UTC)  # Tuesday, while the market is open


class CountingPriceData(InMemoryPriceData):
    """Counts the requests for closes that reach the provider."""

    def __init__(self) -> None:
        super().__init__()
        self.requests = 0

    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        self.requests += 1
        return super().closes_between(symbol, start, end)

    def latest_prices(self, symbols: Collection[str]) -> dict[str, Quote]:
        self.requests += 1
        self.asked_for = list(symbols)
        return super().latest_prices(symbols)


def close(day: date, price: str) -> Quote:
    return Quote(Decimal(price), Currency.USD, datetime(day.year, day.month, day.day, 4, 0, tzinfo=UTC))


def provider() -> CountingPriceData:
    prices = CountingPriceData()
    prices.add_close(SYMBOL, close(THURSDAY, "120.00"))
    prices.add_close(SYMBOL, close(FRIDAY, "123.54"))
    prices.add_close(SYMBOL, close(MONDAY, "124.30"))
    return prices


def test_past_closes_are_fetched_once_even_after_a_restart(tmp_path: Path) -> None:
    source = provider()

    first = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW)).closes_between(SYMBOL, FRIDAY, SUNDAY)
    again = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW)).closes_between(SYMBOL, FRIDAY, SUNDAY)

    assert again == first == {day: close(FRIDAY, "123.54") for day in (FRIDAY, date(2024, 6, 29), SUNDAY)}
    assert source.requests == 1


def test_a_symbol_without_closes_is_remembered_too(tmp_path: Path) -> None:
    source = provider()
    prices = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW))

    assert prices.closes_between("ZZZZ", FRIDAY, SUNDAY) == prices.closes_between("ZZZZ", FRIDAY, SUNDAY) == {}
    assert source.requests == 1


def test_a_single_close_comes_from_the_cache(tmp_path: Path) -> None:
    source = provider()
    prices = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW))
    prices.closes_between(SYMBOL, FRIDAY, SUNDAY)

    assert prices.close_on(SYMBOL, SUNDAY) == close(FRIDAY, "123.54")
    assert source.requests == 1


def test_earlier_days_are_fetched_when_asked_for(tmp_path: Path) -> None:
    source = provider()
    prices = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW))
    prices.closes_between(SYMBOL, FRIDAY, SUNDAY)

    assert prices.closes_between(SYMBOL, THURSDAY, SUNDAY)[THURSDAY] == close(THURSDAY, "120.00")


def test_todays_closes_are_fetched_again_once_they_may_have_changed(tmp_path: Path) -> None:
    source = provider()
    clock = FixedClock(NOW)
    prices = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", clock)
    assert prices.closes_between(SYMBOL, MONDAY, TUESDAY)[TUESDAY] == close(MONDAY, "124.30")  # no close today yet

    source.add_close(SYMBOL, close(TUESDAY, "125.00"))
    clock.set(NOW + FRESH_FOR - timedelta(minutes=1))
    assert prices.closes_between(SYMBOL, MONDAY, TUESDAY)[TUESDAY] == close(MONDAY, "124.30")
    clock.set(NOW + FRESH_FOR)
    assert prices.closes_between(SYMBOL, MONDAY, TUESDAY)[TUESDAY] == close(TUESDAY, "125.00")

    assert source.requests == 2


def test_another_provider_does_not_share_the_cache(tmp_path: Path) -> None:
    source = provider()
    CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", FixedClock(NOW)).closes_between(SYMBOL, FRIDAY, SUNDAY)

    CachedPriceData(source, "alpaca/sip", tmp_path / "cache.sqlite", FixedClock(NOW)).closes_between(SYMBOL, FRIDAY, SUNDAY)

    assert source.requests == 2


def test_latest_prices_are_kept_for_a_minute_and_only_missing_ones_asked_for(tmp_path: Path) -> None:
    source = provider()
    source.set(SYMBOL, close(TUESDAY, "125.00"))
    source.set("AAPL", close(TUESDAY, "230.00"))
    clock = FixedClock(NOW)
    prices = CachedPriceData(source, SOURCE, tmp_path / "cache.sqlite", clock)

    assert prices.latest_prices([SYMBOL])[SYMBOL].price == Decimal("125.00")
    both = prices.latest_prices([SYMBOL, "AAPL"])  # the first is still fresh: only the second is asked for
    assert (sorted(both), source.asked_for, prices.latest_price(SYMBOL)) == (["AAPL", SYMBOL], ["AAPL"], both[SYMBOL])
    clock.set(NOW + LATEST_FRESH_FOR)
    prices.latest_prices([SYMBOL])

    assert source.requests == 3
