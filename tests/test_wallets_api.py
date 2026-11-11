from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.interfaces.web import create_app


def client_for(db: Path) -> TestClient:
    return TestClient(create_app(SqliteWalletRepository(db)))


def test_created_wallet_is_stored_and_can_be_read_back(tmp_path: Path) -> None:
    db = tmp_path / "test.db"

    created = client_for(db).post(
        "/wallets", json={"name": "Long term", "currency": "EUR", "cash": "1000.50"}
    )
    assert created.status_code == 201
    wallet_id = created.json()["id"]

    # A fresh app on the same file proves the wallet was persisted, not just kept in memory.
    fetched = client_for(db).get(f"/wallets/{wallet_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": wallet_id,
        "name": "Long term",
        "currency": "EUR",
        "cash": "1000.50",
    }


def test_unknown_wallet_returns_404(tmp_path: Path) -> None:
    response = client_for(tmp_path / "test.db").get(f"/wallets/{uuid4()}")
    assert response.status_code == 404
