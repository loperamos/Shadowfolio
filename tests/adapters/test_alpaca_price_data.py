"""How the Alpaca adapter talks HTTP, with the network replaced by a fake transport.

The fake responses below are written by hand. The live tests at the end check them against the
real API, so the offline tests cannot drift from what Alpaca actually sends.
"""

import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2
import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.alpaca_price_data import BASE_URL, AlpacaConfig, AlpacaPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceDataUnavailableError

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


BARS_BODY = '{"bars": [{"t": "2024-06-24T14:26:00Z", "o": 122.005, "h": 122.04, "l": 121.78, "c": 121.815, "v": 5832}], "symbol": "NVDA"}'


def test_historical_price_is_the_open_of_the_first_minute_bar_at_or_after_the_time() -> None:
    seen: list[httpx2.Request] = []
    at = datetime(2024, 6, 24, 14, 26, tzinfo=UTC)

    quote = adapter_answering(200, BARS_BODY, seen).price_at("NVDA", at)

    assert quote == Quote(Decimal("122.005"), Currency.USD, at)
    params = seen[0].url.params
    assert seen[0].url.path == "/v2/stocks/NVDA/bars"
    assert (params["timeframe"], params["start"], params["limit"], params["sort"], params["adjustment"]) == (
        "1Min",
        "2024-06-24T14:26:00Z",
        "1",
        "asc",
        "raw",
    )


DAILY_BARS_BODY = (
    '{"bars": [{"t": "2024-06-28T04:00:00Z", "o": 124.58, "h": 127.71, "l": 122.75, "c": 123.54, "v": 31005}], "symbol": "NVDA"}'
)


def test_close_on_a_day_is_the_close_of_the_last_daily_bar_up_to_its_end() -> None:
    seen: list[httpx2.Request] = []

    quote = adapter_answering(200, DAILY_BARS_BODY, seen).close_on("NVDA", date(2024, 6, 30))

    assert quote == Quote(Decimal("123.54"), Currency.USD, datetime(2024, 6, 28, 4, 0, tzinfo=UTC))
    params = seen[0].url.params
    assert (params["timeframe"], params["end"], params["limit"], params["sort"], params["adjustment"]) == (
        "1Day",
        "2024-06-30T23:59:59.999999Z",
        "1",
        "desc",
        "raw",
    )


def test_no_bars_means_no_historical_price() -> None:
    # Alpaca answers unknown symbols with 200 and no bars.
    assert adapter_answering(200, '{"bars": null, "symbol": "ZZZZ"}').price_at("ZZZZ", datetime(2024, 6, 24, tzinfo=UTC)) is None


@pytest.mark.parametrize("status", UNKNOWN_SYMBOL_STATUSES)
def test_unknown_symbol_is_none(status: int) -> None:
    assert adapter_answering(status, '{"message": "not found"}').latest_price("ZZZZ") is None


@pytest.mark.parametrize("fetch", ["latest", "historical", "close"])
def test_other_errors_mean_prices_are_unavailable(fetch: str) -> None:
    adapter = adapter_answering(500, "oops")
    with pytest.raises(PriceDataUnavailableError):
        if fetch == "latest":
            adapter.latest_price("NVDA")
        elif fetch == "historical":
            adapter.price_at("NVDA", datetime(2024, 6, 24, 14, 26, tzinfo=UTC))
        else:
            adapter.close_on("NVDA", date(2024, 6, 30))


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


@pytest.mark.live
def test_real_bars_have_the_shape_the_fake_uses() -> None:
    response = _real_client().get(
        "/v2/stocks/NVDA/bars", params={"timeframe": "1Min", "start": "2024-06-24T14:26:00Z", "limit": 1, "feed": "iex"}
    )

    assert response.status_code == 200
    real, fake = json.loads(response.text), json.loads(BARS_BODY)
    assert fake.keys() <= real.keys()
    assert fake["bars"][0].keys() <= real["bars"][0].keys()
    assert isinstance(real["bars"][0]["o"], int | float)
