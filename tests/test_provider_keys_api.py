"""A user's own market-data keys: saved per provider, shown back only by a hint (never the secret), replaced or removed
by their owner, and seen by no one else."""

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.wiring.test import build_test_app

ANA, BEN = "auth0|ana", "auth0|ben"
ALPACA = {"key_id": "PKTEST1234ABCD", "secret": "alpaca-secret-never-shown"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(identity=InMemoryIdentity({"ana-token": ANA, "ben-token": BEN})))


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_saved_key_is_listed_by_a_hint_never_by_its_secret(client: TestClient) -> None:
    saved = client.put("/api/provider-keys/alpaca", json=ALPACA, headers=as_user("ana-token"))

    assert saved.status_code == 200
    assert saved.json() == {"provider": "alpaca", "hint": "ABCD", "saved_at": "2026-01-05T15:00:00Z"}
    assert client.get("/api/provider-keys", headers=as_user("ana-token")).json() == [saved.json()]
    assert "never-shown" not in client.get("/api/provider-keys", headers=as_user("ana-token")).text


def test_a_key_with_a_single_part_is_hinted_by_its_end(client: TestClient) -> None:
    saved = client.put("/api/provider-keys/finnhub", json={"secret": " finnhub-key-9876 "}, headers=as_user("ana-token"))

    assert saved.json()["hint"] == "9876"


@pytest.mark.parametrize(
    ("provider", "body", "message"),
    [
        ("alpaca", {"secret": "s"}, "Alpaca needs a key id and a secret key"),
        ("alpaca", {"key_id": " ", "secret": "s"}, "Alpaca needs a key id and a secret key"),
        ("finnhub", {"secret": "  "}, "the key must not be blank"),
        ("finnhub", {"key_id": "x", "secret": "s"}, "Finnhub takes a single key, without a key id"),
    ],
)
def test_a_key_missing_a_part_is_refused(client: TestClient, provider: str, body: dict[str, str], message: str) -> None:
    response = client.put(f"/api/provider-keys/{provider}", json=body, headers=as_user("ana-token"))

    assert response.status_code == 422
    assert response.json() == {"detail": message}


def test_saving_again_replaces_the_key_and_removing_it_forgets_it(client: TestClient) -> None:
    client.put("/api/provider-keys/alpaca", json=ALPACA, headers=as_user("ana-token"))
    client.put("/api/provider-keys/alpaca", json={"key_id": "PKOTHER9999", "secret": "s2"}, headers=as_user("ana-token"))

    assert [key["hint"] for key in client.get("/api/provider-keys", headers=as_user("ana-token")).json()] == ["9999"]
    assert client.delete("/api/provider-keys/alpaca", headers=as_user("ana-token")).status_code == 204
    assert client.get("/api/provider-keys", headers=as_user("ana-token")).json() == []
    assert client.delete("/api/provider-keys/alpaca", headers=as_user("ana-token")).status_code == 404


def test_each_user_sees_and_removes_only_their_own_keys(client: TestClient) -> None:
    client.put("/api/provider-keys/alpaca", json=ALPACA, headers=as_user("ana-token"))

    assert client.get("/api/provider-keys", headers=as_user("ben-token")).json() == []
    assert client.delete("/api/provider-keys/alpaca", headers=as_user("ben-token")).status_code == 404
    assert len(client.get("/api/provider-keys", headers=as_user("ana-token")).json()) == 1
