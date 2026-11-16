"""Access tokens for agents: created with a name, a scope (read, or trading: read and place or cancel orders now) and
the wallets they may use. The secret is given once, when created: only a hash of it is kept. A token can be revoked."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW)))


def a_wallet(client: TestClient, name: str = "W") -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": name, "currency": "USD", "cash": "100"}).json()["id"]
    return wallet_id


def create(client: TestClient, **body: Any) -> Any:
    return client.post("/api/access-tokens", json={"name": "Codex on my laptop", "scope": "trading", **body})


def test_a_token_is_created_with_its_secret_given_once(client: TestClient) -> None:
    wallet_id = a_wallet(client)

    created = create(client, wallet_ids=[wallet_id])

    assert created.status_code == 201
    body = created.json()
    secret = body["secret"]
    assert secret.startswith("sfo_") and len(secret) > 40  # a prefix, for secret scanners, and plenty of randomness
    token = body["token"]
    assert (token["name"], token["scope"], token["wallet_ids"], token["created_at"]) == (
        "Codex on my laptop",
        "trading",
        [wallet_id],
        "2026-03-02T15:00:00Z",
    )
    assert (token["hint"], token["last_used_at"], token["revoked_at"]) == (secret[:8], None, None)
    # Listed without the secret, which is not kept.
    [listed] = client.get("/api/access-tokens").json()
    assert listed == token and secret not in str(listed)


@pytest.mark.parametrize(
    "body", [{"wallet_ids": []}, {"wallet_ids": ["00000000-0000-0000-0000-000000000000"]}, {"name": " ", "wallet_ids": None}]
)
def test_a_token_needs_a_name_and_existing_wallets(client: TestClient, body: dict[str, Any]) -> None:
    wallet_id = a_wallet(client)
    if body.get("wallet_ids") is None:
        body = {**body, "wallet_ids": [wallet_id]}

    assert create(client, **body).status_code == 422


def test_a_revoked_token_stays_listed_as_revoked(client: TestClient) -> None:
    token_id = create(client, wallet_ids=[a_wallet(client)]).json()["token"]["id"]

    revoked = client.post(f"/api/access-tokens/{token_id}/revoke")

    assert (revoked.status_code, revoked.json()["revoked_at"]) == (200, "2026-03-02T15:00:00Z")
    assert client.get("/api/access-tokens").json()[0]["revoked_at"] == "2026-03-02T15:00:00Z"
    assert client.post("/api/access-tokens/00000000-0000-0000-0000-000000000000/revoke").status_code == 404
