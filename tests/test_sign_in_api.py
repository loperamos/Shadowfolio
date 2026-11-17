"""Every API request needs a signed-in user (Authorization: Bearer <token>), and each user sees only their own
wallets and access tokens: another user's wallet answers as one that does not exist. Open: the sign-in settings the
frontend needs to sign in, and the jobs the system runs for every wallet."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_identity import FixedIdentity
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.interfaces.web.app import SignInSettings
from shadowfolio.wiring.test import JOB, build_test_app

ANA, BEN = "auth0|ana", "auth0|ben"
SETTINGS = SignInSettings(provider="auth0", domain="tenant.eu.auth0.com", client_id="spa-client", audience="https://shadowfolio/api")


@pytest.fixture
def client() -> TestClient:
    identity = InMemoryIdentity({"ana-token": ANA, "ben-token": BEN})
    return TestClient(build_test_app(identity=identity, sign_in=SETTINGS))


def as_user(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def anas_wallet(client: TestClient) -> str:
    body = {"name": "Ana's", "currency": "EUR", "cash": "1000"}
    wallet_id: str = client.post("/api/wallets", json=body, headers=as_user("ana-token")).json()["id"]
    return wallet_id


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic abc"}])
def test_without_a_valid_sign_in_nothing_is_answered(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/api/wallets", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_each_user_sees_only_their_own_wallets(client: TestClient) -> None:
    wallet_id = anas_wallet(client)

    assert [w["id"] for w in client.get("/api/wallets", headers=as_user("ana-token")).json()] == [wallet_id]
    assert client.get("/api/wallets", headers=as_user("ben-token")).json() == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/wallets/{id}", None),
        ("get", "/api/wallets/{id}/valuation", None),
        ("get", "/api/wallets/{id}/operations", None),
        ("post", "/api/wallets/{id}/deposits", {"amount": "5", "timestamp": "2026-01-05T09:00:00Z"}),
        ("delete", "/api/wallets/{id}", None),
    ],
)
def test_another_users_wallet_answers_as_one_that_does_not_exist(client: TestClient, method: str, path: str, body: Any) -> None:
    wallet_id = anas_wallet(client)

    response = client.request(method, path.format(id=wallet_id), json=body, headers=as_user("ben-token"))

    assert response.status_code == 404
    assert client.get(f"/api/wallets/{wallet_id}", headers=as_user("ana-token")).status_code == 200  # still there


def test_access_tokens_belong_to_their_user_and_only_for_their_wallets(client: TestClient) -> None:
    wallet_id = anas_wallet(client)
    body = {"name": "agent", "scope": "read", "wallet_ids": [wallet_id]}

    assert client.post("/api/access-tokens", json=body, headers=as_user("ben-token")).status_code == 422  # not his wallet
    assert client.post("/api/access-tokens", json=body, headers=as_user("ana-token")).status_code == 201
    assert len(client.get("/api/access-tokens", headers=as_user("ana-token")).json()) == 1
    assert client.get("/api/access-tokens", headers=as_user("ben-token")).json() == []


def test_the_sign_in_settings_and_the_systems_jobs_need_no_user(client: TestClient) -> None:
    assert client.get("/api/auth/config").json() == {
        "provider": "auth0",
        "domain": "tenant.eu.auth0.com",
        "client_id": "spa-client",
        "audience": "https://shadowfolio/api",
        "user_id": None,
    }
    # Jobs need the job secret, not a user (see test_jobs_api).
    assert client.post("/api/sync", headers=JOB).status_code == 200
    assert client.post("/api/orders/fill", headers=JOB).status_code == 200


def test_without_sign_in_set_up_it_says_so() -> None:
    client = TestClient(build_test_app(identity=InMemoryIdentity({}, unavailable="sign-in is not set up: set AUTH0_DOMAIN")))

    response = client.get("/api/wallets", headers=as_user("any"))

    assert (response.status_code, response.json()["detail"]) == (503, "sign-in is not set up: set AUTH0_DOMAIN")
    assert client.get("/api/auth/config").json() is None


def test_acting_as_a_fixed_user_needs_no_sign_in_and_tells_the_frontend() -> None:
    """For screenshots of signed-in pages on the developer's machine: every request is that user's, and the frontend
    is told so, to skip the provider's sign-in. Only the screenshot entry point builds it (see wiring.screenshot)."""
    fixed = SignInSettings(provider="fixed", user_id=ANA)
    client = TestClient(build_test_app(identity=FixedIdentity(ANA), sign_in=fixed))
    wallet_id = client.post("/api/wallets", json={"name": "Ana's", "currency": "EUR", "cash": "10"}).json()["id"]

    assert [w["id"] for w in client.get("/api/wallets").json()] == [wallet_id]
    assert client.get("/api/auth/config").json() == {
        "provider": "fixed",
        "domain": None,
        "client_id": None,
        "audience": None,
        "user_id": ANA,
    }
