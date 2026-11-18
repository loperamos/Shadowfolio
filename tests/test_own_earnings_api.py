"""When companies report next comes from the user's own Finnhub key (saved in Settings), only ever shown to them. The key
is optional: without one, only the earnings date is missing, and it says why; admins without one use the server's."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_earnings_calendar import InMemoryEarningsCalendar
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.earnings import EarningsDate, EarningsTime
from shadowfolio.domain.provider_keys import ProviderKey
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.market_data import MarketData
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
ADMIN, ANA, BEN = "auth0|admin", "auth0|ana", "auth0|ben"
ANAS_DATE, SERVERS_DATE = date(2026, 3, 20), date(2026, 3, 27)


@pytest.fixture
def http() -> Iterator[TestClient]:
    identity = InMemoryIdentity({"admin-token": ADMIN, "ana-token": ANA, "ben-token": BEN})

    def with_key(_: str, __: ProviderKey) -> MarketData:
        return MarketData(InMemoryPriceData(), InMemoryCorporateActions(), InMemoryNews())

    def calendar(key: ProviderKey) -> EarningsCalendar:
        assert key.secret == "ana-finnhub"
        return InMemoryEarningsCalendar(EarningsDate("NVDA", ANAS_DATE, EarningsTime.AFTER_CLOSE))

    app = build_test_app(
        clock=FixedClock(NOW),
        earnings_calendar=InMemoryEarningsCalendar(EarningsDate("NVDA", SERVERS_DATE, EarningsTime.AFTER_CLOSE)),
        identity=identity,
        admins=(ADMIN,),
        own_keys=with_key,
        own_earnings=calendar,
    )
    with TestClient(app) as client:
        yield client


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def connect(http: TestClient, token: str, provider: str, body: dict[str, str]) -> None:
    assert http.put(f"/api/provider-keys/{provider}", json=body, headers=as_user(token)).status_code == 200


def earnings(http: TestClient, token: str) -> tuple[int, object]:
    response = http.get("/api/securities/NVDA/earnings", headers=as_user(token))
    return response.status_code, response.json()


def test_earnings_dates_come_from_the_users_own_finnhub_key(http: TestClient) -> None:
    connect(http, "ana-token", "alpaca", {"key_id": "PKANA", "secret": "ana-alpaca"})
    connect(http, "ana-token", "finnhub", {"secret": "ana-finnhub"})

    assert earnings(http, "ana-token") == (200, {"next_date": ANAS_DATE.isoformat(), "time": "after_close"})
    assert earnings(http, "admin-token") == (200, {"next_date": SERVERS_DATE.isoformat(), "time": "after_close"})


def test_without_a_finnhub_key_only_the_earnings_date_is_missing(http: TestClient) -> None:
    connect(http, "ben-token", "alpaca", {"key_id": "PKBEN", "secret": "ben-alpaca"})

    assert earnings(http, "ben-token") == (422, {"detail": "connect your Finnhub key in Settings to see earnings dates"})
    summary = http.get("/api/securities/NVDA/summary", headers=as_user("ben-token")).json()
    assert "connect your Finnhub key in Settings to see earnings dates" in summary["unavailable"]
    assert http.get("/api/me", headers=as_user("ben-token")).json()["missing_keys"] == []  # optional: no banner
