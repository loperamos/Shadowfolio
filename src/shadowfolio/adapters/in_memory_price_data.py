"""PriceData holding quotes, minute bars and daily closes in memory, for tests."""

from datetime import date, datetime, timedelta

from shadowfolio.domain.market import MinuteBar
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData


class InMemoryPriceData(PriceData):
    def __init__(self, quotes: dict[str, Quote] | None = None) -> None:
        self._quotes = dict(quotes or {})
        self._bars: dict[str, list[MinuteBar]] = {}  # per symbol, oldest first
        self._closes: dict[str, list[Quote]] = {}  # per symbol: each trading day's close, as of that day

    def set(self, symbol: str, quote: Quote) -> None:
        self._quotes[symbol] = quote

    def add_bar(self, symbol: str, bar: Quote) -> None:
        """A minute bar that only traded at one price: `bar.price` is its open (and high and low), `bar.as_of` its time."""
        self.add_minute_bar(symbol, MinuteBar(bar.as_of, bar.price, bar.price, bar.price, bar.currency))

    def add_minute_bar(self, symbol: str, bar: MinuteBar) -> None:
        self._bars.setdefault(symbol, []).append(bar)
        self._bars[symbol].sort(key=lambda b: b.as_of)

    def add_close(self, symbol: str, close: Quote) -> None:
        """A trading day's close: `close.price` is the close and `close.as_of` the day."""
        self._closes.setdefault(symbol, []).append(close)
        self._closes[symbol].sort(key=lambda c: c.as_of)

    def latest_price(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)

    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        bar = next((bar for bar in self._bars.get(symbol, []) if bar.as_of >= at), None)
        return None if bar is None else Quote(bar.open, bar.currency, bar.as_of)

    def minute_bars(self, symbol: str, start: datetime, end: datetime) -> list[MinuteBar]:
        return [bar for bar in self._bars.get(symbol, []) if start <= bar.as_of <= end]

    def close_on(self, symbol: str, day: date) -> Quote | None:
        return next((close for close in reversed(self._closes.get(symbol, [])) if close.as_of.date() <= day), None)

    def closes_between(self, symbol: str, start: date, end: date) -> dict[date, Quote]:
        days = (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        return {day: close for day in days if (close := self.close_on(symbol, day)) is not None}
