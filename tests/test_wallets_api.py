from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW)))


def create_wallet(client: TestClient, cash: str) -> str:
    response = client.post("/wallets", json={"name": "Long term", "currency": "EUR", "cash": cash})
    assert response.status_code == 201
    wallet_id: str = response.json()["id"]
    return wallet_id


def test_created_wallet_can_be_read_back(client: TestClient) -> None:
    wallet_id = create_wallet(client, "1000.50")

    fetched = client.get(f"/wallets/{wallet_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": wallet_id,
        "name": "Long term",
        "currency": "EUR",
        "cash": "1000.50",
    }


def test_starting_cash_and_deposits_are_recorded_as_operations(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")
    client.post(f"/wallets/{wallet_id}/deposits", json={"amount": "50.25"})

    operations = client.get(f"/wallets/{wallet_id}/operations").json()
    assert [(op["type"], op["timestamp"], op["amount"]) for op in operations] == [
        ("deposit", "2026-03-02T15:00:00Z", "100"),
        ("deposit", "2026-03-02T15:00:00Z", "50.25"),
    ]
    assert client.get(f"/wallets/{wallet_id}").json()["cash"] == "150.25"


def test_wallet_without_starting_cash_has_no_operations(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")

    assert client.get(f"/wallets/{wallet_id}/operations").json() == []
    assert client.get(f"/wallets/{wallet_id}").json()["cash"] == "0"


def test_negative_starting_cash_is_rejected(client: TestClient) -> None:
    response = client.post("/wallets", json={"name": "X", "currency": "EUR", "cash": "-1"})
    assert response.status_code == 422


def test_withdrawal_takes_cash_out_and_is_recorded(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/wallets/{wallet_id}/withdrawals", json={"amount": "30.50"})
    assert response.status_code == 200
    assert response.json()["cash"] == "69.50"
    operations = client.get(f"/wallets/{wallet_id}/operations").json()
    assert [(op["type"], op["amount"]) for op in operations] == [
        ("deposit", "100"),
        ("withdrawal", "30.50"),
    ]


def test_withdrawing_more_than_cash_is_rejected(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/wallets/{wallet_id}/withdrawals", json={"amount": "100.01"})
    assert response.status_code == 422
    assert len(client.get(f"/wallets/{wallet_id}/operations").json()) == 1


@pytest.mark.parametrize("operation", ["deposits", "withdrawals"])
@pytest.mark.parametrize("amount", ["0", "-1"])
def test_amount_must_be_positive(client: TestClient, operation: str, amount: str) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/wallets/{wallet_id}/{operation}", json={"amount": amount})
    assert response.status_code == 422
    assert len(client.get(f"/wallets/{wallet_id}/operations").json()) == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/wallets/{id}"),
        ("GET", "/wallets/{id}/operations"),
        ("POST", "/wallets/{id}/deposits"),
        ("POST", "/wallets/{id}/withdrawals"),
    ],
)
def test_unknown_wallet_returns_404(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path.format(id=uuid4()), json={"amount": "10"})
    assert response.status_code == 404
