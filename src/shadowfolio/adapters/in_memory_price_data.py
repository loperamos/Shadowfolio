"""PriceData holding quotes, minute bars and daily closes in memory, for tests."""

from datetime import date, datetime

from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceData


class InMemoryPriceData(PriceData):
    def __init__(self, quotes: dict[str, Quote] | None = None) -> None:
        self._quotes = dict(quotes or {})
        self._bars: dict[str, list[Quote]] = {}  # per symbol: each bar's open price, at the bar's time
        self._closes: dict[str, list[Quote]] = {}  # per symbol: each trading day's close, as of that day

    def set(self, symbol: str, quote: Quote) -> None:
        self._quotes[symbol] = quote

    def add_bar(self, symbol: str, bar: Quote) -> None:
        """A minute bar: `bar.price` is its open and `bar.as_of` its time."""
        self._bars.setdefault(symbol, []).append(bar)
        self._bars[symbol].sort(key=lambda b: b.as_of)

    def add_close(self, symbol: str, close: Quote) -> None:
        """A trading day's close: `close.price` is the close and `close.as_of` the day."""
        self._closes.setdefault(symbol, []).append(close)
        self._closes[symbol].sort(key=lambda c: c.as_of)

    def latest_price(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)

    def price_at(self, symbol: str, at: datetime) -> Quote | None:
        return next((bar for bar in self._bars.get(symbol, []) if bar.as_of >= at), None)

    def close_on(self, symbol: str, day: date) -> Quote | None:
        return next((close for close in reversed(self._closes.get(symbol, [])) if close.as_of.date() <= day), None)
