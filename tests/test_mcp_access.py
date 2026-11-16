"""Every request to the MCP server needs an access token (Authorization: Bearer <secret>). A token only reaches the
wallets it was granted, and only a trading token places or cancels orders."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def http(clock: FixedClock) -> Iterator[TestClient]:
    """The app, started once (as a server does), called as a local client: the web API and the MCP server."""
    prices = InMemoryPriceData({"NVDA": Quote(Decimal("100"), Currency.USD, NOW - timedelta(minutes=1))})
    with TestClient(build_test_app(clock=clock, prices=prices), base_url="http://127.0.0.1:8000") as client:
        yield client


def setup(http: TestClient, scope: str) -> tuple[str, str, str]:
    """Two wallets, and a token of `scope` granted the first: its id, the other's id, and the secret."""
    granted, other = (http.post("/api/wallets", json={"name": n, "currency": "USD", "cash": "1000"}).json()["id"] for n in ("A", "B"))
    secret = http.post("/api/access-tokens", json={"name": "agent", "scope": scope, "wallet_ids": [granted]}).json()["secret"]
    return granted, other, secret


def call(http: TestClient, tool: str, secret: str | None, **arguments: Any) -> Any:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    headers = ACCEPT | ({"Authorization": f"Bearer {secret}"} if secret else {})
    return http.post("/mcp", json=request, headers=headers)


def text_of(response: Any) -> str:
    text: str = response.json()["result"]["content"][0]["text"]
    return text


@pytest.mark.parametrize("secret", [None, "sfo_not-a-real-token"])
def test_without_a_valid_token_nothing_is_answered(http: TestClient, secret: str | None) -> None:
    setup(http, "read")

    response = call(http, "list_wallets", secret)

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    assert "access token" in response.json()["error"]


def test_a_token_reaches_only_its_wallets(http: TestClient) -> None:
    granted, other, secret = setup(http, "read")

    listed = call(http, "list_wallets", secret).json()["result"]["structuredContent"]["result"]
    hidden = call(http, "wallet_snapshot", secret, wallet_id=other)

    assert [wallet["id"] for wallet in listed] == [granted]
    assert hidden.json()["result"]["isError"] and f"no wallet {other}" in text_of(hidden)


def test_only_a_trading_token_places_orders(http: TestClient) -> None:
    granted, _, read_secret = setup(http, "read")
    order = {"wallet_id": granted, "side": "buy", "symbol": "NVDA", "quantity": "1", "reason": "Try"}

    refused = call(http, "place_order", read_secret, **order)
    previewed = call(http, "preview_order", read_secret, wallet_id=granted, side="buy", symbol="NVDA", quantity="1")

    assert refused.json()["result"]["isError"] and "only reads" in text_of(refused)
    assert not previewed.json()["result"]["isError"]  # a preview places nothing
    trading_wallet, _, trading_secret = setup(http, "trading")
    placed = call(http, "place_order", trading_secret, **{**order, "wallet_id": trading_wallet})
    assert placed.json()["result"]["structuredContent"]["status"] == "open"


def test_a_revoked_token_no_longer_works_and_use_is_recorded(http: TestClient, clock: FixedClock) -> None:
    _, _, secret = setup(http, "read")
    token_id = http.get("/api/access-tokens").json()[0]["id"]

    clock.set(NOW + timedelta(hours=1))
    assert call(http, "list_wallets", secret).status_code == 200
    assert http.get("/api/access-tokens").json()[0]["last_used_at"] == "2026-03-02T16:00:00Z"
    http.post(f"/api/access-tokens/{token_id}/revoke")

    assert call(http, "list_wallets", secret).status_code == 401
