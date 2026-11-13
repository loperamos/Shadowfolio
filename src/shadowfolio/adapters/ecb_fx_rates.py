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

from shadowfolio.adapters.daily import last_on_or_before
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError

DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
# Daily reference rates over a period, one currency against the euro: {currency} → e.g. USD.
HISTORY_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
# How far back to look for a published rate before a requested day (weekends and holidays have none).
HISTORY_LOOKBACK = timedelta(days=7)
TIMEOUT_SECONDS = 10.0


class EcbFxRates(FxRates):
    def __init__(self, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """`clock` tells which years are over (their rates are fetched once and kept); `transport` replaces the network in tests."""
        self._clock = clock
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)
        # Past years' rates never change: per currency and year, every published (day, units per euro), oldest first.
        self._past_years: dict[tuple[Currency, int], list[tuple[date, Decimal]]] = {}

    def latest_rate(self, base: Currency, quote: Currency) -> FxRate | None:
        try:
            as_of, per_euro = self._daily_rates()
        except httpx2.HTTPError as error:
            raise FxRatesUnavailableError(f"ECB: {error}") from error
        per_euro[Currency.EUR] = Decimal(1)
        if base not in per_euro or quote not in per_euro:
            return None
        # Units of `quote` per euro, divided by units of `base` per euro.
        return FxRate(base=base, quote=quote, rate=per_euro[quote] / per_euro[base], as_of=as_of)

    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        per_euro: dict[Currency, tuple[date, Decimal]] = {}
        for currency in {base, quote} - {Currency.EUR}:
            try:
                found = self._per_euro_on(currency, day)
            except httpx2.HTTPError as error:
                raise FxRatesUnavailableError(f"ECB: {error}") from error
            if found is None:
                return None
            per_euro[currency] = found
        as_of = min((published for published, _ in per_euro.values()), default=day)
        rates = {currency: rate for currency, (_, rate) in per_euro.items()} | {Currency.EUR: Decimal(1)}
        return FxRate(base=base, quote=quote, rate=rates[quote] / rates[base], as_of=as_of)

    def rates_between(self, base: Currency, quote: Currency, start: date, end: date) -> dict[date, FxRate]:
        """One request per currency other than the euro, for the whole period."""
        per_euro: dict[Currency, dict[date, tuple[date, Decimal]]] = {}
        for currency in {base, quote} - {Currency.EUR}:
            try:
                series = self._series(currency, start - HISTORY_LOOKBACK, end)
            except httpx2.HTTPError as error:
                raise FxRatesUnavailableError(f"ECB: {error}") from error
            per_euro[currency] = last_on_or_before(((day, (day, rate)) for day, rate in series), start, end, HISTORY_LOOKBACK)
        rates: dict[date, FxRate] = {}
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if any(day not in days for days in per_euro.values()):
                continue
            found = {currency: days[day] for currency, days in per_euro.items()}
            as_of = min((published for published, _ in found.values()), default=day)
            units = {currency: rate for currency, (_, rate) in found.items()} | {Currency.EUR: Decimal(1)}
            rates[day] = FxRate(base=base, quote=quote, rate=units[quote] / units[base], as_of=as_of)
        return rates

    def _per_euro_on(self, currency: Currency, day: date) -> tuple[date, Decimal] | None:
        """Units of `currency` per euro on `day`, or on the last day before it (within a week) with a published rate."""
        if day.year < self._clock.now().year:
            series = self._past_year(currency, day.year)
        else:  # the current year still grows every working day, so ask for just the days needed
            series = self._series(currency, day - HISTORY_LOOKBACK, day)
        earlier = [(published, rate) for published, rate in series if day - HISTORY_LOOKBACK <= published <= day]
        return earlier[-1] if earlier else None

    def _past_year(self, currency: Currency, year: int) -> list[tuple[date, Decimal]]:
        """A finished year's rates (and the week before it, for the first days of January), fetched once."""
        key = (currency, year)
        if key not in self._past_years:
            self._past_years[key] = self._series(currency, date(year, 1, 1) - HISTORY_LOOKBACK, date(year, 12, 31))
        return self._past_years[key]

    def _series(self, currency: Currency, start: date, end: date) -> list[tuple[date, Decimal]]:
        """Every published (day, units per euro) from `start` to `end`, oldest first."""
        params = {"startPeriod": start.isoformat(), "endPeriod": end.isoformat(), "format": "csvdata"}
        response = self._client.get(HISTORY_URL.format(currency=currency.value), params=params)
        if response.status_code == HTTPStatus.NOT_FOUND:  # no observations in the period
            return []
        response.raise_for_status()
        rows = [row for row in csv.DictReader(io.StringIO(response.text)) if row.get("OBS_VALUE")]
        return sorted((date.fromisoformat(row["TIME_PERIOD"]), Decimal(row["OBS_VALUE"])) for row in rows)

    def _daily_rates(self) -> tuple[date, dict[Currency, Decimal]]:
        """The publication date and, for each supported currency, its units per euro."""
        response = self._client.get(DAILY_RATES_URL)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        day = next(cube for cube in root.iter() if "time" in cube.attrib)
        supported = {c.value for c in Currency}
        rates = {Currency(c.attrib["currency"]): Decimal(c.attrib["rate"]) for c in day if c.attrib.get("currency") in supported}
        return date.fromisoformat(day.attrib["time"]), rates
