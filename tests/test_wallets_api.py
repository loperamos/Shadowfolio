from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shadowfolio.wiring.test import build_test_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app())


def test_created_wallet_can_be_read_back(client: TestClient) -> None:
    created = client.post(
        "/wallets", json={"name": "Long term", "currency": "EUR", "cash": "1000.50"}
    )
    assert created.status_code == 201
    wallet_id = created.json()["id"]

    fetched = client.get(f"/wallets/{wallet_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": wallet_id,
        "name": "Long term",
        "currency": "EUR",
        "cash": "1000.50",
    }


def test_deposit_adds_cash_to_the_stored_wallet(client: TestClient) -> None:
    wallet_id = client.post(
        "/wallets", json={"name": "Long term", "currency": "EUR", "cash": "100"}
    ).json()["id"]

    deposited = client.post(f"/wallets/{wallet_id}/deposits", json={"amount": "50.25"})
    assert deposited.status_code == 200
    assert deposited.json()["cash"] == "150.25"
    assert client.get(f"/wallets/{wallet_id}").json()["cash"] == "150.25"


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_deposit_must_be_positive(client: TestClient, amount: str) -> None:
    wallet_id = client.post(
        "/wallets", json={"name": "Long term", "currency": "EUR", "cash": "100"}
    ).json()["id"]

    response = client.post(f"/wallets/{wallet_id}/deposits", json={"amount": amount})
    assert response.status_code == 422
    assert client.get(f"/wallets/{wallet_id}").json()["cash"] == "100"


def test_deposit_to_unknown_wallet_returns_404(client: TestClient) -> None:
    response = client.post(f"/wallets/{uuid4()}/deposits", json={"amount": "10"})
    assert response.status_code == 404


def test_unknown_wallet_returns_404(client: TestClient) -> None:
    response = client.get(f"/wallets/{uuid4()}")
    assert response.status_code == 404
