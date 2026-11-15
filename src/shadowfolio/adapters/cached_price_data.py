"""PriceData that keeps daily closes in a file in front of a provider, so each is fetched once (see DailyCache).

Latest prices are kept in memory for LATEST_FRESH_FOR, so a page valuing several wallets that hold the same symbol asks
for it once; minute bars are always asked of the provider.
"""

from collections.abc import Collection
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from shadowfolio.adapters.daily_cache import DailyCache, Fields
from shadowfolio.domain.market import MinuteBar
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.price_data import PriceData

# How long a latest price is used before it is asked for again: prices move, but not much within a minute.
LATEST_FRESH_FOR = timedelta(minutes=1)


class CachedPriceData(PriceData):
    def __init__(self, provider: PriceData, source: str, path: Path, clock: Clock) -> None:
        """`source` names the provider and its plan or feed, e.g. "alpaca/iex"; `path` is the cache file."""
        self._provider = provider
        self._closes = DailyCache(path, source, clock, _encode, _decode)
        self._clock = clock
        self._latest: dict[str, tuple[datetime, Quote | None]] = {}  # per symbol: when it was asked for, and its price

    def latest_price(self, symbol: str) -> Quote | None:
        return self.latest_prices([symbol]).get(symbol)

    def latest_prices(self, symbols: Collection[str]) -> dict[str, Quote]:
        now = self._clock.now()
        missing = [symbol for symbol in symbols if symbol not in self._latest or now - self._latest[symbol][0] >= LATEST_FRESH_FOR]
        if missing:
            found = self._provider.latest_prices(missing)
            for symbol in missing:  # a symbol without a price is remembered too
                self._latest[symbol] = (now, found.get(symbol))
        quotes = {symbol: self._latest[symbol][1] for symbol in symbols}
        return {symbol: quote for symbol, quote in quotes.items() if quote is not None}

    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        return self._provider.price_at(symbol, at)

    def minute_bars(self, symbol: str, start: datetime, end: datetime) -> list[MinuteBar]:
        return self._provider.minute_bars(symbol, start, end)

    def close_on(self, symbol: str, day: date) -> Quote | None:
        return self.closes_between(symbol, day, day).get(day)

    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        return self._closes.between(symbol, start, end, lambda first, last: self._provider.closes_between(symbol, first, last))


def _encode(quote: Quote) -> Fields:
    previous = None if quote.previous_close is None else str(quote.previous_close)
    volume = None if quote.volume is None else str(quote.volume)
    return [str(quote.price), quote.currency.value, quote.as_of.isoformat(), previous, volume]


def _decode(fields: Fields) -> Quote:
    price, currency, as_of, previous, volume = fields
    assert price is not None and currency is not None and as_of is not None
    return Quote(
        Decimal(price),
        Currency(currency),
        datetime.fromisoformat(as_of),
        None if previous is None else Decimal(previous),
        None if volume is None else Decimal(volume),
    )
