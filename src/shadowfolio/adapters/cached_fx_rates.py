"""FxRates that keeps daily rates in a file in front of a provider, so each is fetched once (see DailyCache).

The latest rate is always asked of the provider.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from shadowfolio.adapters.daily_cache import DailyCache, Fields
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates

PAIR_SEPARATOR = "/"


class CachedFxRates(FxRates):
    def __init__(self, provider: FxRates, source: str, path: Path, clock: Clock) -> None:
        """`source` names the provider, e.g. "ecb"; `path` is the cache file."""
        self._provider = provider
        self._rates = DailyCache(path, source, clock, _encode, _decode)

    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        return self._provider.latest_rate(base, quote)

    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        return self.rates_between(base, quote, day, day).get(day)

    def rates_between(self, base: Currency, quote: Currency, start: date, end: date) -> dict[date, FxRate]:
        pair = f"{base.value}{PAIR_SEPARATOR}{quote.value}"
        return self._rates.between(pair, start, end, lambda first, last: self._provider.rates_between(base, quote, first, last))


def _encode(rate: FxRate) -> Fields:
    return [rate.base.value, rate.quote.value, str(rate.rate), rate.as_of.isoformat()]


def _decode(fields: Fields) -> FxRate:
    base, quote, rate, as_of = fields
    assert base is not None and quote is not None and rate is not None and as_of is not None
    return FxRate(Currency(base), Currency(quote), Decimal(rate), date.fromisoformat(as_of))
