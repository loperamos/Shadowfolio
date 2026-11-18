"""Each user's market data is fetched with their own key (saved in Settings), so what one key fetches is only ever
shown to its owner: their wallets' values and dividends, their security pages, and their agents' answers. Admins
without a key of their own use the server's; anyone else is asked to connect one."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.money import Currency
from shadowfolio.domain.provider_keys import ProviderKey
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.market_data import MarketData
from shadowfolio.wiring.test import JOB, build_test_app

NOW = datetime(2024, 6, 20, 15, 0, tzinfo=UTC)
ADMIN, ANA, BEN = "auth0|admin", "auth0|ana", "auth0|ben"
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
NVDA_DIVIDEND = DividendEvent("NVDA", date(2024, 6, 10), date(2024, 6, 17), Decimal("0.50"), Currency.USD, "nvda-2024-06")
MISSING_KEY = "connect your Alpaca key in Settings to get market data"


def provider(price: str, *events: DividendEvent) -> MarketData:
    prices = InMemoryPriceData({"NVDA": Quote(Decimal(price), Currency.USD, NOW - timedelta(minutes=1))})
    return MarketData(prices, InMemoryCorporateActions(*events), InMemoryNews())


# What each key fetches: Ana's provider knows NVDA's dividend, Ben's does not; the server's has its own price.
BY_SECRET = {"ana-secret": provider("100", NVDA_DIVIDEND), "ben-secret": provider("200")}
SERVER = provider("300")


@pytest.fixture
def http() -> Iterator[TestClient]:
    identity = InMemoryIdentity({"admin-token": ADMIN, "ana-token": ANA, "ben-token": BEN})

    def with_key(_: str, key: ProviderKey) -> MarketData:
        return BY_SECRET[key.secret]

    app = build_test_app(
        clock=FixedClock(NOW),
        prices=SERVER.prices,
        corporate_actions=SERVER.corporate_actions,
        identity=identity,
        admins=(ADMIN,),
        own_keys=with_key,
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def connect(http: TestClient, token: str, secret: str) -> None:
    body = {"key_id": f"PK{secret}", "secret": secret}
    assert http.put("/api/provider-keys/alpaca", json=body, headers=as_user(token)).status_code == 200


def quote(http: TestClient, token: str) -> Any:
    return http.get("/api/market/quotes/NVDA", headers=as_user(token))


def wallet_holding_nvda(http: TestClient, token: str) -> str:
    wallet_id: str = http.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}, headers=as_user(token)).json()["id"]
    http.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "1000", "timestamp": "2024-01-02T09:00:00Z"}, headers=as_user(token))
    buy = {"symbol": "NVDA", "quantity": "2", "price": "90", "price_currency": "USD", "timestamp": "2024-05-01T15:00:00Z"}
    response = http.post(f"/api/wallets/{wallet_id}/buys", json=buy, headers=as_user(token))
    assert response.status_code == 200, response.json()
    return wallet_id


def test_each_user_sees_prices_fetched_with_their_own_key(http: TestClient) -> None:
    connect(http, "ana-token", "ana-secret")
    connect(http, "ben-token", "ben-secret")

    assert quote(http, "ana-token").json()["price"] == "100"
    assert quote(http, "ben-token").json()["price"] == "200"
    assert quote(http, "admin-token").json()["price"] == "300"  # an admin without a key of their own: the server's


def test_without_a_key_a_user_is_asked_to_connect_one(http: TestClient) -> None:
    connect(http, "ana-token", "ana-secret")

    refused = quote(http, "ben-token")
    assert refused.status_code == 422
    assert refused.json() == {"detail": MISSING_KEY}
    missing = {
        token: http.get("/api/me", headers=as_user(token)).json()["missing_keys"] for token in ("ana-token", "ben-token", "admin-token")
    }
    assert missing == {"ana-token": [], "ben-token": ["alpaca"], "admin-token": []}


def test_a_wallet_is_valued_and_credited_dividends_with_its_owners_key(http: TestClient) -> None:
    connect(http, "ana-token", "ana-secret")
    connect(http, "ben-token", "ben-secret")
    anas, bens = wallet_holding_nvda(http, "ana-token"), wallet_holding_nvda(http, "ben-token")

    assert http.get(f"/api/wallets/{anas}/valuation", headers=as_user("ana-token")).json()["total"] == "1021.00"  # 820 + 1 + 2 × 100
    assert http.get(f"/api/wallets/{bens}/valuation", headers=as_user("ben-token")).json()["total"] == "1220.00"  # 820 + 2 × 200
    assert http.get(f"/api/wallets/{anas}", headers=as_user("ana-token")).json()["cash"] == "821.00"  # Ana's provider's dividend
    assert http.get(f"/api/wallets/{bens}", headers=as_user("ben-token")).json()["cash"] == "820"  # none from his


def test_the_daily_jobs_skip_wallets_whose_owner_has_no_key(http: TestClient) -> None:
    connect(http, "ana-token", "ana-secret")
    connect(http, "ben-token", "ben-secret")
    anas, _ = wallet_holding_nvda(http, "ana-token"), wallet_holding_nvda(http, "ben-token")
    http.delete("/api/provider-keys/alpaca", headers=as_user("ben-token"))

    assert http.post("/api/sync", headers=JOB).status_code == 200
    assert http.post("/api/orders/fill", headers=JOB).status_code == 200
    assert http.get(f"/api/wallets/{anas}", headers=as_user("ana-token")).json()["cash"] == "821.00"


def test_an_agent_gets_its_owners_market_data(http: TestClient) -> None:
    connect(http, "ana-token", "ana-secret")
    wallet_id = wallet_holding_nvda(http, "ana-token")
    body = {"name": "agent", "scope": "read", "wallet_ids": [wallet_id]}
    secret = http.post("/api/access-tokens", json=body, headers=as_user("ana-token")).json()["secret"]

    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "security_summary", "arguments": {"symbol": "NVDA"}}}
    summary = http.post("/mcp", json=request, headers=ACCEPT | {"Authorization": f"Bearer {secret}"}).json()

    assert summary["result"]["structuredContent"]["price"] == "100"
