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
        "holdings": {},
    }


def test_wallets_are_listed_in_creation_order(client: TestClient) -> None:
    assert client.get("/wallets").json() == []
    first = create_wallet(client, "10")
    second = create_wallet(client, "20")

    listed = client.get("/wallets").json()
    assert [(w["id"], w["cash"]) for w in listed] == [(first, "10"), (second, "20")]


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


def fund_in_the_past(client: TestClient, wallet_id: str, amount: str) -> None:
    response = client.post(
        f"/wallets/{wallet_id}/deposits",
        json={"amount": amount, "timestamp": "2024-01-02T09:00:00Z"},
    )
    assert response.status_code == 200


# Values from a real DEGIRO statement: 8 NVDA at 121.81 USD, settled 907.68 EUR, 2.00 EUR fees.
NVDA_BUY = {
    "symbol": "NVDA",
    "quantity": "8",
    "price": "121.81",
    "price_currency": "USD",
    "timestamp": "2024-06-24T14:26:00Z",
    "settled_amount": "907.68",
    "fees": "2.00",
}


def test_past_buy_in_foreign_currency_uses_settled_amount_and_fees(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")

    response = client.post(f"/wallets/{wallet_id}/buys", json=NVDA_BUY)
    assert response.status_code == 200
    assert response.json()["cash"] == "90.32"
    assert response.json()["holdings"] == {"NVDA": "8"}
    buy = client.get(f"/wallets/{wallet_id}/operations").json()[-1]
    assert {k: buy[k] for k in ("type", "timestamp", "amount", "fees", "price")} == {
        "type": "buy",
        "timestamp": "2024-06-24T14:26:00Z",
        "amount": "907.68",
        "fees": "2.00",
        "price": "121.81",
    }


def test_buy_in_wallet_currency_costs_quantity_times_price(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "2000")

    response = client.post(
        f"/wallets/{wallet_id}/buys",
        json={
            "symbol": "TSLA",
            "quantity": "5",
            "price": "295.05",
            "price_currency": "EUR",
            "timestamp": "2024-11-15T13:39:00Z",
            "fees": "3.90",
        },
    )
    assert response.json()["cash"] == "520.85"  # 2000 - 5 × 295.05 - 3.90


def test_foreign_currency_buy_without_settled_amount_is_rejected(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")

    response = client.post(f"/wallets/{wallet_id}/buys", json={**NVDA_BUY, "settled_amount": None})
    assert response.status_code == 422


def test_buy_before_the_cash_arrived_is_rejected(client: TestClient) -> None:
    # The wallet has enough cash now, but the starting deposit is dated after the buy.
    wallet_id = create_wallet(client, "5000")

    response = client.post(f"/wallets/{wallet_id}/buys", json=NVDA_BUY)
    assert response.status_code == 422
    assert client.get(f"/wallets/{wallet_id}").json()["holdings"] == {}


@pytest.mark.parametrize(
    "change",
    [
        {"timestamp": "2026-03-02T15:01:00Z"},  # after now
        {"timestamp": "2024-06-24T14:26:00"},  # no timezone
        {"quantity": "0"},
        {"price": "-1"},
        {"fees": "-1"},
    ],
)
def test_invalid_buy_is_rejected(client: TestClient, change: dict[str, str]) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")

    response = client.post(f"/wallets/{wallet_id}/buys", json={**NVDA_BUY, **change})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/wallets/{id}"),
        ("GET", "/wallets/{id}/operations"),
        ("POST", "/wallets/{id}/deposits"),
        ("POST", "/wallets/{id}/withdrawals"),
        ("POST", "/wallets/{id}/buys"),
    ],
)
def test_unknown_wallet_returns_404(client: TestClient, method: str, path: str) -> None:
    body = NVDA_BUY if path.endswith("buys") else {"amount": "10"}
    response = client.request(method, path.format(id=uuid4()), json=body)
    assert response.status_code == 404
