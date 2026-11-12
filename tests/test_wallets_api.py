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


def test_unknown_wallet_returns_404(client: TestClient) -> None:
    response = client.get(f"/wallets/{uuid4()}")
    assert response.status_code == 404
