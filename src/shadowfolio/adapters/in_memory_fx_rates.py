"""FxRates holding rates in memory, for tests."""

from datetime import date

from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRates


class InMemoryFxRates(FxRates):
    def __init__(self, *rates: FxRate) -> None:
        self._rates: dict[tuple[Currency, Currency], list[FxRate]] = {}
        for rate in rates:
            self.set(rate)

    def set(self, rate: FxRate) -> None:
        """Adds a daily rate; the latest by date is the current one."""
        history = self._rates.setdefault((rate.base, rate.quote), [])
        history.append(rate)
        history.sort(key=lambda r: r.as_of)

    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        history = self._rates.get((base, quote))
        return history[-1] if history else None

    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        earlier = [rate for rate in self._rates.get((base, quote), []) if rate.as_of <= day]
        return earlier[-1] if earlier else None
