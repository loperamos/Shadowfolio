"""Deleting one's account removes everything that is theirs: wallets (with their history and orders), agent tokens,
saved market-data keys, usage counts and the account itself. Signing in again starts a new, empty account."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.wiring.test import build_test_app

ADMIN, BEN = "auth0|admin", "auth0|ben"
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def http() -> Iterator[TestClient]:
    identity = InMemoryIdentity({"admin-token": ADMIN, "ben-token": BEN})
    with TestClient(build_test_app(identity=identity, admins=(ADMIN,)), base_url="http://127.0.0.1:8000") as client:
        yield client


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_deleting_an_account_removes_everything_that_was_theirs(http: TestClient) -> None:
    ben = as_user("ben-token")
    wallet_id = http.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "100"}, headers=ben).json()["id"]
    secret = http.post("/api/access-tokens", json={"name": "agent", "scope": "read", "wallet_ids": [wallet_id]}, headers=ben).json()[
        "secret"
    ]
    http.put("/api/provider-keys/finnhub", json={"secret": "finnhub-key"}, headers=ben)
    admins_wallet = http.post("/api/wallets", json={"name": "Mine", "currency": "USD", "cash": "1"}, headers=as_user("admin-token")).json()[
        "id"
    ]

    assert http.delete("/api/me", headers=ben).status_code == 204

    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_wallets", "arguments": {}}}
    assert http.post("/mcp", json=request, headers=ACCEPT | {"Authorization": f"Bearer {secret}"}).status_code == 401
    assert [user["id"] for user in http.get("/api/users", headers=as_user("admin-token")).json()] == [ADMIN]
    assert {row["user_id"] for row in http.get("/api/usage", headers=as_user("admin-token")).json()} == {ADMIN}
    assert [w["id"] for w in http.get("/api/wallets", headers=as_user("admin-token")).json()] == [admins_wallet]  # others' stay
    # Signing in again: a new, empty account.
    assert http.get("/api/wallets", headers=ben).json() == []
    assert http.get("/api/access-tokens", headers=ben).json() == []
    assert http.get("/api/provider-keys", headers=ben).json() == []
