"""Importing a broker's statement into a wallet over HTTP: preview first, then import."""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_security_lookup import InMemorySecurityLookup
from shadowfolio.wiring.test import build_test_app

TRANSACTIONS_HEADER = (
    "Date,Heure,Produit,Code ISIN,Place boursière sectionnée,Lieu d'exécution,Quantité,Cours,,Montant devise locale,,"
    "Montant EUR,Taux de change,Frais conversion AutoFX,Frais de courtage et/ou de parties,Montant négocié EUR,ID Ordre"
)
ACCOUNT_HEADER = "Date,Heure,Date de,Produit,Code ISIN,Description,FX,Mouvements,,Solde,,ID Ordre"
DEPOSIT = '02-01-2025,10:00,02-01-2025,,,Dépôt flatex,,EUR,"1000,00",EUR,"1000,00",'
BUY = '03-01-2025,14:39,TESLA INC,US88160R1014,TDG,XGAT,2,"300,0000",EUR,"-600,00",EUR,"-600,00","1,0000","0,00","-3,90","-603,90",o1'
STATEMENT = {"transactions": f"{TRANSACTIONS_HEADER}\n{BUY}", "account": f"{ACCOUNT_HEADER}\n{DEPOSIT}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(security_lookup=InMemorySecurityLookup({"US88160R1014": "TSLA"})))


def new_wallet(client: TestClient) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "DEGIRO", "currency": "EUR", "cash": "0"}).json()["id"]
    return wallet_id


def test_a_preview_shows_the_wallet_after_the_import_without_saving_it(client: TestClient) -> None:
    wallet_id = new_wallet(client)

    response = client.post(f"/api/wallets/{wallet_id}/imports/degiro/preview", json=STATEMENT)

    assert response.status_code == 200
    preview = response.json()
    assert (preview["can_import"], preview["imported"], preview["records"], preview["problems"]) == (True, False, 2, [])
    assert (Decimal(preview["cash"]), preview["holdings"]) == (Decimal("396.10"), {"TSLA": "2"})  # 1000 - 600 - 3.90
    assert client.get(f"/api/wallets/{wallet_id}/operations").json() == []


def test_an_import_saves_the_operations(client: TestClient) -> None:
    wallet_id = new_wallet(client)

    response = client.post(f"/api/wallets/{wallet_id}/imports/degiro", json=STATEMENT)

    assert (response.status_code, response.json()["imported"]) == (200, True)
    wallet = client.get(f"/api/wallets/{wallet_id}").json()
    assert (Decimal(wallet["cash"]), wallet["holdings"]) == (Decimal("396.10"), {"TSLA": "2"})


def test_a_statement_with_problems_is_reported_and_not_imported(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    unknown = '04-01-2025,10:00,04-01-2025,,,Something new,,EUR,"1,00",EUR,"397,10",'
    statement = {**STATEMENT, "account": f"{ACCOUNT_HEADER}\n{unknown}\n{DEPOSIT}"}

    response = client.post(f"/api/wallets/{wallet_id}/imports/degiro", json=statement)

    assert response.status_code == 200
    result = response.json()
    assert (result["can_import"], result["imported"]) == (False, False)
    assert result["problems"] == [{"date": "2025-01-04", "kind": "unknown", "description": "Something new", "reason": "unknown row"}]
    assert client.get(f"/api/wallets/{wallet_id}/operations").json() == []


def test_a_file_that_is_not_a_degiro_export_is_refused(client: TestClient) -> None:
    wallet_id = new_wallet(client)

    response = client.post(f"/api/wallets/{wallet_id}/imports/degiro/preview", json={**STATEMENT, "account": "Date,Amount\n2025-01-02,100"})

    assert response.status_code == 422
    assert response.json()["detail"] == "the account file is not DEGIRO's Account export (CSV, in French)"


def test_importing_into_an_unknown_wallet_returns_404(client: TestClient) -> None:
    assert client.post(f"/api/wallets/{uuid4()}/imports/degiro/preview", json=STATEMENT).status_code == 404
