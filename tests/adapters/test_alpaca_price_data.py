"""How the Alpaca adapter talks HTTP, with the network replaced by a fake transport.

The fake responses below are written by hand. The live tests at the end check them against the
real API, so the offline tests cannot drift from what Alpaca actually sends.
"""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.alpaca_price_data import BASE_URL, AlpacaConfig, AlpacaPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote

CONFIG = AlpacaConfig(key_id="test-key", secret_key="test-secret")


def adapter_answering(status: int, body: str, seen: list[httpx2.Request] | None = None) -> AlpacaPriceData:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status, text=body)

    return AlpacaPriceData(CONFIG, transport=httpx2.MockTransport(handler))


# What the fakes answer, as Alpaca does (trimmed to the fields the adapter reads).
SNAPSHOT_BODY = (
    '{"symbol": "NVDA", "latestTrade": {"t": "2026-03-02T20:59:59.123456789Z", "p": 135.505, "s": 100},'
    ' "prevDailyBar": {"t": "2026-02-27T05:00:00Z", "o": 131.2, "h": 134.0, "l": 130.1, "c": 133.04, "v": 1000}}'
)
UNKNOWN_SYMBOL_STATUSES = [404, 422]


def test_snapshot_becomes_an_exact_usd_quote_with_the_previous_close() -> None:
    seen: list[httpx2.Request] = []

    quote = adapter_answering(200, SNAPSHOT_BODY, seen).latest_price("NVDA")

    assert quote == Quote(Decimal("135.505"), Currency.USD, datetime(2026, 3, 2, 20, 59, 59, 123456, tzinfo=UTC), Decimal("133.04"))
    request = seen[0]
    assert request.url.path == "/v2/stocks/NVDA/snapshot"
    assert request.url.params["feed"] == "iex"
    assert request.headers["APCA-API-KEY-ID"] == "test-key"


def test_snapshot_without_a_previous_day_has_no_previous_close() -> None:
    body = json.dumps({key: value for key, value in json.loads(SNAPSHOT_BODY).items() if key != "prevDailyBar"})

    quote = adapter_answering(200, body).latest_price("NVDA")

    assert quote is not None and quote.previous_close is None


@pytest.mark.parametrize("status", UNKNOWN_SYMBOL_STATUSES)
def test_unknown_symbol_is_none(status: int) -> None:
    assert adapter_answering(status, '{"message": "not found"}').latest_price("ZZZZ") is None


def test_other_errors_are_raised() -> None:
    with pytest.raises(httpx2.HTTPStatusError):
        adapter_answering(500, "oops").latest_price("NVDA")


def _real_client() -> httpx2.Client:
    load_dotenv()
    key_id, secret_key = os.environ.get("ALPACA_API_KEY_ID"), os.environ.get("ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        pytest.skip("Alpaca credentials are not set")
    return httpx2.Client(base_url=BASE_URL, headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key})


@pytest.mark.live
def test_real_snapshot_has_the_shape_the_fake_uses() -> None:
    response = _real_client().get("/v2/stocks/NVDA/snapshot", params={"feed": "iex"})

    assert response.status_code == 200
    real, fake = json.loads(response.text), json.loads(SNAPSHOT_BODY)
    assert fake.keys() <= real.keys()
    for part in ("latestTrade", "prevDailyBar"):
        assert fake[part].keys() <= real[part].keys()
    assert isinstance(real["latestTrade"]["p"], int | float)
    assert isinstance(real["prevDailyBar"]["c"], int | float)
    assert datetime.fromisoformat(real["latestTrade"]["t"]).utcoffset() is not None


@pytest.mark.live
def test_real_unknown_symbol_answers_a_status_the_fake_uses() -> None:
    response = _real_client().get("/v2/stocks/ZZZZZZZZ/snapshot", params={"feed": "iex"})

    assert response.status_code in UNKNOWN_SYMBOL_STATUSES
