"""Contract every SecurityLookup adapter must meet.

Runs against the in-memory fake by default; OpenFIGI runs only with `pytest -m live` (network, no key needed).
"""

from collections.abc import Callable

import pytest

from shadowfolio.adapters.in_memory_security_lookup import InMemorySecurityLookup
from shadowfolio.adapters.openfigi_security_lookup import OpenFigiSecurityLookup
from shadowfolio.ports.security_lookup import SecurityLookup

APPLE, BERKSHIRE_B, SAP = "US0378331005", "US0846707026", "DE0007164600"
TRADEGATE = "XGAT"
NOT_AN_ISIN = "US0IPOSPACEX"  # a broker's temporary line, as DEGIRO books IPO subscriptions


def _in_memory() -> SecurityLookup:
    return InMemorySecurityLookup({APPLE: "AAPL", BERKSHIRE_B: "BRK.B", SAP: "SAP.XGAT"})


ADAPTERS: dict[str, Callable[[], SecurityLookup]] = {"in_memory": _in_memory, "openfigi": OpenFigiSecurityLookup}


@pytest.fixture(params=["in_memory", pytest.param("openfigi", marks=pytest.mark.live)])
def lookup(request: pytest.FixtureRequest) -> SecurityLookup:
    return ADAPTERS[request.param]()


def test_us_securities_get_their_us_tickers_as_market_data_writes_them(lookup: SecurityLookup) -> None:
    assert lookup.tickers({APPLE: None, BERKSHIRE_B: "XNYS"}) == {APPLE: "AAPL", BERKSHIRE_B: "BRK.B"}


def test_another_security_gets_its_ticker_on_its_venue_tagged_with_it(lookup: SecurityLookup) -> None:
    assert lookup.tickers({SAP: TRADEGATE}) == {SAP: "SAP.XGAT"}


def test_what_is_not_a_real_isin_is_left_out(lookup: SecurityLookup) -> None:
    assert lookup.tickers({NOT_AN_ISIN: None}) == {}
