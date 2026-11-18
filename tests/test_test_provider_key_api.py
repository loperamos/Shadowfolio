"""A saved key can be tested: one small request to its provider says whether it works, and if not, why."""

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_key_checker import InMemoryKeyChecker
from shadowfolio.wiring.test import build_test_app

REFUSED = "Alpaca refused this key: check that you copied both parts whole"


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(key_checker=InMemoryKeyChecker({"bad-secret": REFUSED})))


def test_a_working_key_says_so(client: TestClient) -> None:
    client.put("/api/provider-keys/alpaca", json={"key_id": "PKID", "secret": "good-secret"})

    response = client.post("/api/provider-keys/alpaca/test")

    assert response.status_code == 200
    assert response.json() == {"works": True, "message": "Alpaca answered with this key."}


def test_a_key_that_does_not_work_says_why(client: TestClient) -> None:
    client.put("/api/provider-keys/alpaca", json={"key_id": "PKID", "secret": "bad-secret"})

    assert client.post("/api/provider-keys/alpaca/test").json() == {"works": False, "message": REFUSED}


def test_only_a_saved_key_can_be_tested(client: TestClient) -> None:
    assert client.post("/api/provider-keys/finnhub/test").status_code == 404
