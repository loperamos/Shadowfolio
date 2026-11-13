"""FxRates from the European Central Bank's daily euro reference rates.

Free, no key, and allowed to be shown to users. The ECB publishes one rate per currency against
the euro on each working day, around 16:00 CET; other pairs are derived from those.
"""

import csv
import io
import xml.etree.ElementTree as ElementTree
from datetime import date, timedelta
from decimal import Decimal
from http import HTTPStatus

import httpx2

from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRates

DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
# Daily reference rates over a period, one currency against the euro: {currency} → e.g. USD.
HISTORY_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
# How far back to look for a published rate before a requested day (weekends and holidays have none).
HISTORY_LOOKBACK = timedelta(days=7)
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

    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        per_euro: dict[Currency, tuple[date, Decimal]] = {}
        for currency in {base, quote} - {Currency.EUR}:
            found = self._per_euro_on(currency, day)
            if found is None:
                return None
            per_euro[currency] = found
        as_of = min((published for published, _ in per_euro.values()), default=day)
        rates = {currency: rate for currency, (_, rate) in per_euro.items()} | {Currency.EUR: Decimal(1)}
        return FxRate(base=base, quote=quote, rate=rates[quote] / rates[base], as_of=as_of)

    def _per_euro_on(self, currency: Currency, day: date) -> tuple[date, Decimal] | None:
        """Units of `currency` per euro on `day`, or on the last day before it with a published rate."""
        params = {"startPeriod": (day - HISTORY_LOOKBACK).isoformat(), "endPeriod": day.isoformat(), "format": "csvdata"}
        response = self._client.get(HISTORY_URL.format(currency=currency.value), params=params)
        if response.status_code == HTTPStatus.NOT_FOUND:  # no observations in the period
            return None
        response.raise_for_status()
        rows = [row for row in csv.DictReader(io.StringIO(response.text)) if row.get("OBS_VALUE")]
        if not rows:
            return None
        latest = max(rows, key=lambda row: row["TIME_PERIOD"])
        return date.fromisoformat(latest["TIME_PERIOD"]), Decimal(latest["OBS_VALUE"])

    def _daily_rates(self) -> tuple[date, dict[Currency, Decimal]]:
        """The publication date and, for each supported currency, its units per euro."""
        response = self._client.get(DAILY_RATES_URL)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        day = next(cube for cube in root.iter() if "time" in cube.attrib)
        supported = {c.value for c in Currency}
        rates = {Currency(c.attrib["currency"]): Decimal(c.attrib["rate"]) for c in day if c.attrib.get("currency") in supported}
        return date.fromisoformat(day.attrib["time"]), rates
