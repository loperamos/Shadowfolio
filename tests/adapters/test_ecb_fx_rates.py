"""How the ECB adapter reads the daily rates, with the network replaced by a fake transport.

The fake feed below is written by hand, trimmed from the real one. The live test at the end
checks it against the real feed, so the offline tests cannot drift from what the ECB publishes.
"""

import xml.etree.ElementTree as ElementTree
from datetime import date
from decimal import Decimal

import httpx2
import pytest

from shadowfolio.adapters.ecb_fx_rates import DAILY_RATES_URL, EcbFxRates
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


@pytest.mark.live
def test_real_feed_has_the_shape_the_fake_uses() -> None:
    response = httpx2.get(DAILY_RATES_URL)

    assert response.status_code == 200
    day = next(cube for cube in ElementTree.fromstring(response.text).iter() if "time" in cube.attrib)
    date.fromisoformat(day.attrib["time"])
    usd = [cube for cube in day if cube.attrib.get("currency") == "USD"]
    assert len(usd) == 1
    assert Decimal(usd[0].attrib["rate"]) > 0
