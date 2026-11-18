"""How a saved key is checked: one small request to its provider, with the network replaced by a fake transport. A key
that works says so; one the provider refuses, or that cannot be checked now, says why in plain words, never with the
request (which carries the key)."""

from datetime import UTC, datetime

import httpx2
import pytest

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.http_key_checker import HttpKeyChecker
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
ALPACA = ProviderKey("ana", DataProvider.ALPACA, "PKID", "alpaca-secret", NOW)
FINNHUB = ProviderKey("ana", DataProvider.FINNHUB, None, "finnhub-key", NOW)


def checker(status: int, seen: list[httpx2.Request] | None = None) -> HttpKeyChecker:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status, json={})

    return HttpKeyChecker(FixedClock(NOW), transport=httpx2.MockTransport(handler))


def test_a_working_alpaca_key_is_sent_in_its_headers() -> None:
    seen: list[httpx2.Request] = []

    assert checker(200, seen).check(ALPACA) is None
    assert (seen[0].headers["APCA-API-KEY-ID"], seen[0].headers["APCA-API-SECRET-KEY"]) == ("PKID", "alpaca-secret")
    assert "alpaca-secret" not in str(seen[0].url)


def test_a_working_finnhub_key_is_sent_in_its_header() -> None:
    seen: list[httpx2.Request] = []

    assert checker(200, seen).check(FINNHUB) is None
    assert seen[0].headers["X-Finnhub-Token"] == "finnhub-key"


@pytest.mark.parametrize(
    ("key", "status", "reason"),
    [
        (ALPACA, 401, "Alpaca refused this key: check that you copied both parts whole"),
        (ALPACA, 403, "Alpaca refused this key: check that you copied both parts whole"),
        (FINNHUB, 401, "Finnhub refused this key: check that you copied it whole"),
        (FINNHUB, 429, "Finnhub is limiting requests with this key right now; try again in a minute"),
        (ALPACA, 500, "could not reach Alpaca right now; try again later"),
    ],
)
def test_a_key_that_does_not_work_says_why(key: ProviderKey, status: int, reason: str) -> None:
    assert checker(status).check(key) == reason


def test_a_provider_that_cannot_be_reached_says_so() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no network", request=request)

    assert HttpKeyChecker(FixedClock(NOW), transport=httpx2.MockTransport(handler)).check(FINNHUB) == (
        "could not reach Finnhub right now; try again later"
    )
