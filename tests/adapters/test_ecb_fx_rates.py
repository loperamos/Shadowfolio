"""How the ECB adapter reads the daily rates, with the network replaced by a fake transport.

The fake feed below is written by hand, trimmed from the real one. The live test at the end
checks it against the real feed, so the offline tests cannot drift from what the ECB publishes.
"""

import xml.etree.ElementTree as ElementTree
from datetime import date
from decimal import Decimal

import httpx2
import pytest

from shadowfolio.adapters.ecb_fx_rates import DAILY_RATES_URL, HISTORY_URL, EcbFxRates
from shadowfolio.domain.money import Currency, FxRate

DAILY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time='2026-11-12'>
      <Cube currency='USD' rate='1.1081'/>
      <Cube currency='JPY' rate='176.96'/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


def adapter_serving(feed: str) -> EcbFxRates:
    return EcbFxRates(transport=httpx2.MockTransport(lambda request: httpx2.Response(200, text=feed)))


def test_euro_rates_are_read_exactly() -> None:
    assert adapter_serving(DAILY_FEED).latest_rate(Currency.EUR, Currency.USD) == FxRate(
        Currency.EUR, Currency.USD, Decimal("1.1081"), date(2026, 11, 12)
    )


def test_rates_into_the_euro_are_inverted() -> None:
    rate = adapter_serving(DAILY_FEED).latest_rate(Currency.USD, Currency.EUR)

    assert rate == FxRate(Currency.USD, Currency.EUR, Decimal(1) / Decimal("1.1081"), date(2026, 11, 12))


def test_currency_missing_from_the_feed_has_no_rate() -> None:
    feed = DAILY_FEED.replace("<Cube currency='USD' rate='1.1081'/>", "")
    assert adapter_serving(feed).latest_rate(Currency.EUR, Currency.USD) is None


# Trimmed from the ECB data API's CSV: weekdays only, so a Sunday request returns the days before it.
HISTORY_CSV = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-06-20,1.0719,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-06-21,1.0688,A
"""


def test_historical_rate_is_the_last_published_on_or_before_the_day() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, text=HISTORY_CSV)

    rate = EcbFxRates(transport=httpx2.MockTransport(handler)).rate_on(Currency.EUR, Currency.USD, date(2024, 6, 23))

    assert rate == FxRate(Currency.EUR, Currency.USD, Decimal("1.0688"), date(2024, 6, 21))
    assert seen[0].url.params["endPeriod"] == "2024-06-23"


def test_no_published_rate_in_the_period_means_none() -> None:
    adapter = EcbFxRates(transport=httpx2.MockTransport(lambda request: httpx2.Response(404, text="No results found.")))
    assert adapter.rate_on(Currency.USD, Currency.EUR, date(1990, 1, 1)) is None


@pytest.mark.live
def test_real_feed_has_the_shape_the_fake_uses() -> None:
    response = httpx2.get(DAILY_RATES_URL)

    assert response.status_code == 200
    day = next(cube for cube in ElementTree.fromstring(response.text).iter() if "time" in cube.attrib)
    date.fromisoformat(day.attrib["time"])
    usd = [cube for cube in day if cube.attrib.get("currency") == "USD"]
    assert len(usd) == 1
    assert Decimal(usd[0].attrib["rate"]) > 0


@pytest.mark.live
def test_real_history_has_the_shape_the_fake_uses() -> None:
    response = httpx2.get(
        HISTORY_URL.format(currency="USD"), params={"startPeriod": "2024-06-16", "endPeriod": "2024-06-23", "format": "csvdata"}
    )

    assert response.status_code == 200
    header = response.text.splitlines()[0].split(",")
    assert {"TIME_PERIOD", "OBS_VALUE"} <= set(header)
