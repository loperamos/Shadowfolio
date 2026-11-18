"""Usage figures, for admins: per day, user and source, how many requests each user made (to the web API and to the
MCP server), and how many calls went to each provider with whose key (counted by the providers' adapters)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
ADMIN, BEN = "auth0|admin", "auth0|ben"
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def http(clock: FixedClock) -> Iterator[TestClient]:
    identity = InMemoryIdentity({"admin-token": ADMIN, "ben-token": BEN})
    with TestClient(build_test_app(clock=clock, identity=identity, admins=(ADMIN,)), base_url="http://127.0.0.1:8000") as client:
        yield client


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def usage(http: TestClient, **period: str) -> Any:
    return http.get("/api/usage", params=period, headers=as_user("admin-token"))


def test_each_users_requests_are_counted_per_day_and_source(http: TestClient, clock: FixedClock) -> None:
    wallet_id = http.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}, headers=as_user("ben-token")).json()["id"]
    body = {"name": "agent", "scope": "read", "wallet_ids": [wallet_id]}
    secret = http.post("/api/access-tokens", json=body, headers=as_user("ben-token")).json()["secret"]
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_wallets", "arguments": {}}}
    http.post("/mcp", json=request, headers=ACCEPT | {"Authorization": f"Bearer {secret}"})
    clock.set(NOW + timedelta(days=1))
    http.get("/api/wallets", headers=as_user("ben-token"))

    rows = usage(http, start="2026-03-02", end="2026-03-03").json()

    bens = [(row["day"], row["source"], row["counter"], row["count"]) for row in rows if row["user_id"] == BEN]
    assert sorted(bens) == [
        ("2026-03-02", "mcp", "requests", 1),
        ("2026-03-02", "web", "requests", 2),
        ("2026-03-03", "web", "requests", 1),
    ]


def test_the_period_defaults_to_the_last_week(http: TestClient, clock: FixedClock) -> None:
    http.get("/api/wallets", headers=as_user("ben-token"))
    clock.set(NOW + timedelta(days=8))

    assert [row for row in usage(http).json() if row["user_id"] == BEN] == []
    clock.set(NOW + timedelta(days=6))
    assert [row["count"] for row in usage(http).json() if row["user_id"] == BEN] == [1]


def test_only_admins_see_usage(http: TestClient) -> None:
    assert http.get("/api/usage", headers=as_user("ben-token")).status_code == 403
