"""The free plan's limits beyond wallets: orders placed a day, agent tokens at once, and requests a minute (to the web
API and the MCP server together). Each is refused with the reason; admins have none of them."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, 20, tzinfo=UTC)  # 20 seconds into a minute
ADMIN, BEN = "auth0|admin", "auth0|ben"
FREE_ORDERS_A_DAY, FREE_TOKENS, FREE_REQUESTS_A_MINUTE = 20, 2, 120
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def http(clock: FixedClock) -> Iterator[TestClient]:
    """The app, started once (as a server does): the web API and the MCP server."""
    prices = InMemoryPriceData({"NVDA": Quote(Decimal("100"), Currency.USD, NOW - timedelta(minutes=1))})
    identity = InMemoryIdentity({"admin-token": ADMIN, "ben-token": BEN})
    app = build_test_app(clock=clock, prices=prices, identity=identity, admins=(ADMIN,))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wallet(http: TestClient, token: str = "ben-token") -> str:
    body = {"name": "W", "currency": "USD", "cash": "100000"}
    wallet_id: str = http.post("/api/wallets", json=body, headers=as_user(token)).json()["id"]
    return wallet_id


def order(http: TestClient, wallet_id: str, token: str = "ben-token") -> Any:
    body = {"side": "buy", "symbol": "NVDA", "quantity": "1", "reason": "test"}
    return http.post(f"/api/wallets/{wallet_id}/orders", json=body, headers=as_user(token))


def token_for(http: TestClient, wallet_id: str, scope: str = "trading", token: str = "ben-token") -> Any:
    body = {"name": "agent", "scope": scope, "wallet_ids": [wallet_id]}
    return http.post("/api/access-tokens", json=body, headers=as_user(token))


def mcp(http: TestClient, secret: str, tool: str, **arguments: Any) -> Any:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return http.post("/mcp", json=request, headers=ACCEPT | {"Authorization": f"Bearer {secret}"})


def test_the_plan_says_what_it_allows(http: TestClient) -> None:
    limits = http.get("/api/me", headers=as_user("ben-token")).json()["limits"]

    assert limits == {
        "wallets": 3,
        "orders_per_day": FREE_ORDERS_A_DAY,
        "access_tokens": FREE_TOKENS,
        "requests_per_minute": FREE_REQUESTS_A_MINUTE,
    }


def test_a_free_user_places_as_many_orders_a_day_as_their_plan_allows(http: TestClient, clock: FixedClock) -> None:
    first, second = wallet(http), wallet(http)
    placed = [order(http, first if n % 2 else second).json()["id"] for n in range(FREE_ORDERS_A_DAY)]  # in any wallet
    http.post(f"/api/wallets/{second}/orders/{placed[0]}/cancel", headers=as_user("ben-token"))  # still counts

    refused = order(http, first)
    assert refused.status_code == 422
    assert refused.json() == {"detail": f"your plan allows {FREE_ORDERS_A_DAY} orders a day; place more tomorrow (UTC)"}

    clock.set(NOW + timedelta(days=1))
    assert order(http, first).status_code == 201


def test_an_agent_is_told_before_placing_an_order_the_plan_would_refuse(http: TestClient) -> None:
    wallet_id = wallet(http)
    secret = token_for(http, wallet_id).json()["secret"]
    for _ in range(FREE_ORDERS_A_DAY):
        order(http, wallet_id)

    preview = mcp(http, secret, "preview_order", wallet_id=wallet_id, side="buy", symbol="NVDA", quantity="1")

    assert (
        preview.json()["result"]["structuredContent"]["refusal"]
        == f"your plan allows {FREE_ORDERS_A_DAY} orders a day; place more tomorrow (UTC)"
    )


def test_a_free_user_has_as_many_agent_tokens_at_once_as_their_plan_allows(http: TestClient) -> None:
    wallet_id = wallet(http)
    tokens = [token_for(http, wallet_id).json()["token"]["id"] for _ in range(FREE_TOKENS)]

    refused = token_for(http, wallet_id)
    assert refused.status_code == 422
    assert refused.json() == {"detail": f"your plan allows {FREE_TOKENS} agent tokens at once; revoke one to make another"}

    http.post(f"/api/access-tokens/{tokens[0]}/revoke", headers=as_user("ben-token"))
    assert token_for(http, wallet_id).status_code == 201


def test_requests_a_minute_count_the_web_api_and_the_mcp_server_together(http: TestClient, clock: FixedClock) -> None:
    wallet_id = wallet(http)
    secret = token_for(http, wallet_id, "read").json()["secret"]
    for _ in range(FREE_REQUESTS_A_MINUTE - 3):  # with the two above, and one through MCP
        assert http.get("/api/wallets", headers=as_user("ben-token")).status_code == 200
    assert mcp(http, secret, "list_wallets").status_code == 200

    refused = http.get("/api/wallets", headers=as_user("ben-token"))
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "40"
    assert refused.json() == {"detail": f"your plan allows {FREE_REQUESTS_A_MINUTE} requests a minute; try again in 40 seconds"}
    assert mcp(http, secret, "list_wallets").status_code == 429

    clock.set(NOW + timedelta(seconds=40))  # the next minute
    assert http.get("/api/wallets", headers=as_user("ben-token")).status_code == 200


def test_an_admin_has_none_of_these_limits(http: TestClient) -> None:
    wallet_id = wallet(http, "admin-token")

    assert all(order(http, wallet_id, "admin-token").status_code == 201 for _ in range(FREE_ORDERS_A_DAY + 1))
    assert all(token_for(http, wallet_id, token="admin-token").status_code == 201 for _ in range(FREE_TOKENS + 1))
    assert all(http.get("/api/me", headers=as_user("admin-token")).status_code == 200 for _ in range(FREE_REQUESTS_A_MINUTE))
