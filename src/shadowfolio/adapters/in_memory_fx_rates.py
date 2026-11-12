"""FxRates holding rates in memory, for tests."""

from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRates


class InMemoryFxRates(FxRates):
    def __init__(self, *rates: FxRate) -> None:
        self._rates = {(r.base, r.quote): r for r in rates}

    def set(self, rate: FxRate) -> None:
        self._rates[(rate.base, rate.quote)] = rate

    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        return self._rates.get((base, quote))
