"""PriceData that keeps daily closes in a file in front of a provider, so each is fetched once (see DailyCache).

Latest and intraday prices are always asked of the provider.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from shadowfolio.adapters.daily_cache import DailyCache, Fields
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.price_data import PriceData


class CachedPriceData(PriceData):
    def __init__(self, provider: PriceData, source: str, path: Path, clock: Clock) -> None:
        """`source` names the provider and its plan or feed, e.g. "alpaca/iex"; `path` is the cache file."""
        self._provider = provider
        self._closes = DailyCache(path, source, clock, _encode, _decode)

    def latest_price(self, symbol: str) -> Quote | None:
        return self._provider.latest_price(symbol)

    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        return self._provider.price_at(symbol, at)

    def close_on(self, symbol: str, day: date) -> Quote | None:
        return self.closes_between(symbol, day, day).get(day)

    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        return self._closes.between(symbol, start, end, lambda first, last: self._provider.closes_between(symbol, first, last))


def _encode(quote: Quote) -> Fields:
    previous = None if quote.previous_close is None else str(quote.previous_close)
    return [str(quote.price), quote.currency.value, quote.as_of.isoformat(), previous]


def _decode(fields: Fields) -> Quote:
    price, currency, as_of, previous = fields
    assert price is not None and currency is not None and as_of is not None
    return Quote(Decimal(price), Currency(currency), datetime.fromisoformat(as_of), None if previous is None else Decimal(previous))
