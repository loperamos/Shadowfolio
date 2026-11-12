"""FxRates from the European Central Bank's daily euro reference rates.

Free, no key, and allowed to be shown to users. The ECB publishes one rate per currency against
the euro on each working day, around 16:00 CET; other pairs are derived from those.
"""

import xml.etree.ElementTree as ElementTree
from datetime import date
from decimal import Decimal

import httpx2

from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRates

DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
TIMEOUT_SECONDS = 10.0


class EcbFxRates(FxRates):
    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)

    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        as_of, per_euro = self._daily_rates()
        per_euro[Currency.EUR] = Decimal(1)
        if base not in per_euro or quote not in per_euro:
            return None
        # Units of `quote` per euro, divided by units of `base` per euro.
        return FxRate(base=base, quote=quote, rate=per_euro[quote] / per_euro[base], as_of=as_of)

    def _daily_rates(self) -> tuple[date, dict[Currency, Decimal]]:
        """The publication date and, for each supported currency, its units per euro."""
        response = self._client.get(DAILY_RATES_URL)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        day = next(cube for cube in root.iter() if "time" in cube.attrib)
        supported = {c.value for c in Currency}
        rates = {Currency(c.attrib["currency"]): Decimal(c.attrib["rate"]) for c in day if c.attrib.get("currency") in supported}
        return date.fromisoformat(day.attrib["time"]), rates
