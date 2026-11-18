"""Signing in for the first time makes an account, on the free plan; admins (from the configuration) have no limits and
set other users' tiers. A plan's limits are checked by the use cases and refused with the reason."""

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.wiring.test import build_test_app

ADMIN, BEN = "google-oauth2|admin", "auth0|ben"
FREE_WALLETS, MEMBER_WALLETS = 3, 10


@pytest.fixture
def client() -> TestClient:
    identity = InMemoryIdentity({"admin-token": ADMIN, "ben-token": BEN})
    return TestClient(build_test_app(identity=identity, admins=(ADMIN,)))


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_wallet(client: TestClient, token: str) -> int:
    return client.post("/api/wallets", json={"name": "Mine", "currency": "USD", "cash": "100"}, headers=as_user(token)).status_code


def test_signing_in_for_the_first_time_makes_an_account_on_the_free_plan(client: TestClient) -> None:
    me = client.get("/api/me", headers=as_user("ben-token"))

    assert me.status_code == 200
    assert me.json() == {"id": BEN, "tier": "free", "limits": {"wallets": FREE_WALLETS}, "created_at": "2026-01-05T15:00:00Z"}


def test_an_admin_from_the_configuration_has_no_limits(client: TestClient) -> None:
    me = client.get("/api/me", headers=as_user("admin-token")).json()

    assert (me["tier"], me["limits"]) == ("admin", {"wallets": None})
    assert all(create_wallet(client, "admin-token") == 201 for _ in range(FREE_WALLETS + 1))


def test_a_free_user_has_as_many_wallets_as_their_plan_allows(client: TestClient) -> None:
    assert [create_wallet(client, "ben-token") for _ in range(FREE_WALLETS)] == [201] * FREE_WALLETS

    refused = client.post("/api/wallets", json={"name": "One more", "currency": "USD", "cash": "0"}, headers=as_user("ben-token"))
    assert refused.status_code == 422
    assert refused.json() == {"detail": f"your plan allows {FREE_WALLETS} wallets; delete one to make another"}
    wallet_id = client.get("/api/wallets", headers=as_user("ben-token")).json()[0]["id"]
    copy = client.post(f"/api/wallets/{wallet_id}/copies", json={"name": "Copy"}, headers=as_user("ben-token"))
    assert copy.status_code == 422

    client.delete(f"/api/wallets/{wallet_id}", headers=as_user("ben-token"))
    assert create_wallet(client, "ben-token") == 201


def test_an_admin_lists_users_and_changes_a_tier(client: TestClient) -> None:
    client.get("/api/me", headers=as_user("ben-token"))

    listed = client.get("/api/users", headers=as_user("admin-token"))
    assert [(user["id"], user["tier"]) for user in listed.json()] == [(BEN, "free"), (ADMIN, "admin")]  # as they first came

    changed = client.put(f"/api/users/{BEN}/tier", json={"tier": "member"}, headers=as_user("admin-token"))
    assert changed.status_code == 200
    assert client.get("/api/me", headers=as_user("ben-token")).json()["limits"] == {"wallets": MEMBER_WALLETS}


def test_only_admins_see_users_or_change_tiers(client: TestClient) -> None:
    client.get("/api/me", headers=as_user("ben-token"))

    assert client.get("/api/users", headers=as_user("ben-token")).status_code == 403
    assert client.put(f"/api/users/{BEN}/tier", json={"tier": "admin"}, headers=as_user("ben-token")).status_code == 403
    assert client.get("/api/me", headers=as_user("ben-token")).json()["tier"] == "free"


def test_a_tier_is_only_set_for_someone_who_has_signed_in(client: TestClient) -> None:
    response = client.put("/api/users/auth0|nobody/tier", json={"tier": "member"}, headers=as_user("admin-token"))

    assert response.status_code == 404
