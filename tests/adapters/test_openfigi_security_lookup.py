"""How the OpenFIGI lookup talks HTTP, with the network replaced by a fake transport.

The fake answers follow OpenFIGI's mapping API (trimmed to the fields the adapter reads); the live contract test
checks the real one.
"""

import json
from typing import Any

import httpx2
import pytest

from shadowfolio.adapters.openfigi_security_lookup import MAPPING_URL, OpenFigiSecurityLookup
from shadowfolio.ports.security_lookup import SecurityLookupUnavailableError


def lookup_answering(answer: Any, seen: list[list[dict[str, str]]], status: int = 200) -> OpenFigiSecurityLookup:
    """A lookup whose every request gets `answer(jobs)` (or `answer` itself when it is not callable)."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        jobs = json.loads(request.content)
        seen.append(jobs)
        body = answer(jobs) if callable(answer) else answer
        return httpx2.Response(status, text=json.dumps(body))

    return OpenFigiSecurityLookup(transport=httpx2.MockTransport(handler))


def listing(ticker: str, exchange: str) -> dict[str, Any]:
    return {"data": [{"ticker": ticker, "exchCode": exchange, "marketSector": "Equity"}]}


def test_a_us_security_gets_its_us_ticker_whatever_venue_it_traded_on() -> None:
    seen: list[list[dict[str, str]]] = []

    tickers = lookup_answering([listing("TSLA", "US")], seen).tickers({"US88160R1014": "XGAT"})

    assert tickers == {"US88160R1014": "TSLA"}
    assert seen == [[{"idType": "ID_ISIN", "idValue": "US88160R1014", "exchCode": "US"}]]


def test_another_security_gets_its_ticker_on_the_venue_it_traded_on_tagged_with_the_venue() -> None:
    seen: list[list[dict[str, str]]] = []

    tickers = lookup_answering([listing("AIR", "FP")], seen).tickers({"NL0000235190": "XPAR"})

    assert tickers == {"NL0000235190": "AIR.XPAR"}
    assert seen == [[{"idType": "ID_ISIN", "idValue": "NL0000235190", "micCode": "XPAR"}]]


def test_a_share_class_is_written_with_a_dot_as_market_data_does() -> None:
    assert lookup_answering([listing("BRK/B", "US")], []).tickers({"US0846707026": None}) == {"US0846707026": "BRK.B"}


def test_what_cannot_be_identified_is_left_out() -> None:
    seen: list[list[dict[str, str]]] = []
    answers = [{"error": "Invalid idValue format."}, {"warning": "No identifier found."}]

    tickers = lookup_answering(answers, seen).tickers({"US0IPOSPACEX": None, "US1234567890": None, "KYG596691041": None})

    assert tickers == {}
    # A non-US security never traded here has no venue to look it up on: it is not asked for.
    assert [job["idValue"] for job in seen[0]] == ["US0IPOSPACEX", "US1234567890"]


def test_many_securities_are_asked_in_batches_of_ten() -> None:
    seen: list[list[dict[str, str]]] = []
    isins = {f"US{number:010d}": None for number in range(12)}

    tickers = lookup_answering(lambda jobs: [listing(f"T{job['idValue'][-2:]}", "US") for job in jobs], seen).tickers(isins)

    assert [len(jobs) for jobs in seen] == [10, 2]
    assert len(tickers) == len(isins)


@pytest.mark.parametrize("status", [429, 500])
def test_errors_mean_the_lookup_is_unavailable(status: int) -> None:
    with pytest.raises(SecurityLookupUnavailableError):
        lookup_answering({"error": "Too many requests"}, [], status=status).tickers({"US0378331005": None})


def test_it_calls_openfigis_mapping_api() -> None:
    urls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        urls.append(str(request.url))
        return httpx2.Response(200, text=json.dumps([listing("AAPL", "US")]))

    OpenFigiSecurityLookup(transport=httpx2.MockTransport(handler)).tickers({"US0378331005": None})

    assert urls == [MAPPING_URL]
