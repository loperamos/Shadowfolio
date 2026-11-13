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
    response = client.post("/api/wallets", json={"name": "Long term", "currency": "EUR", "cash": cash})
    assert response.status_code == 201
    wallet_id: str = response.json()["id"]
    return wallet_id


def test_created_wallet_can_be_read_back(client: TestClient) -> None:
    wallet_id = create_wallet(client, "1000.50")

    fetched = client.get(f"/api/wallets/{wallet_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": wallet_id,
        "name": "Long term",
        "currency": "EUR",
        "cash": "1000.50",
        "holdings": {},
        "cost_basis": {},
        "realized_gain": "0.00",
        "hindsight": False,
        "splits_checked_through": None,
    }


def test_wallets_are_listed_in_creation_order(client: TestClient) -> None:
    assert client.get("/api/wallets").json() == []
    first = create_wallet(client, "10")
    second = create_wallet(client, "20")

    listed = client.get("/api/wallets").json()
    assert [(w["id"], w["cash"]) for w in listed] == [(first, "10"), (second, "20")]


def test_starting_cash_and_deposits_are_recorded_as_operations(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "50.25"})

    operations = client.get(f"/api/wallets/{wallet_id}/operations").json()
    assert [(op["type"], op["timestamp"], op["amount"]) for op in operations] == [
        ("deposit", "2026-03-02T15:00:00Z", "100"),
        ("deposit", "2026-03-02T15:00:00Z", "50.25"),
    ]
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "150.25"


def test_wallet_without_starting_cash_has_no_operations(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")

    assert client.get(f"/api/wallets/{wallet_id}/operations").json() == []
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "0"


def test_negative_starting_cash_is_rejected(client: TestClient) -> None:
    response = client.post("/api/wallets", json={"name": "X", "currency": "EUR", "cash": "-1"})
    assert response.status_code == 422


def test_withdrawal_takes_cash_out_and_is_recorded(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "30.50"})
    assert response.status_code == 200
    assert response.json()["cash"] == "69.50"
    operations = client.get(f"/api/wallets/{wallet_id}/operations").json()
    assert [(op["type"], op["amount"]) for op in operations] == [("deposit", "100"), ("withdrawal", "30.50")]


def test_past_withdrawal_must_fit_the_cash_at_that_time(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")  # on 2024-01-02

    before_funding = client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "10", "timestamp": "2023-12-31T09:00:00Z"})
    assert before_funding.status_code == 422
    after_funding = client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "10", "timestamp": "2024-02-01T09:00:00Z"})
    assert after_funding.json()["cash"] == "990"
    assert client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]["timestamp"] == "2024-02-01T09:00:00Z"


def test_withdrawing_more_than_cash_is_rejected(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "100.01"})
    assert response.status_code == 422
    assert len(client.get(f"/api/wallets/{wallet_id}/operations").json()) == 1


@pytest.mark.parametrize("operation", ["deposits", "withdrawals"])
@pytest.mark.parametrize("amount", ["0", "-1"])
def test_amount_must_be_positive(client: TestClient, operation: str, amount: str) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.post(f"/api/wallets/{wallet_id}/{operation}", json={"amount": amount})
    assert response.status_code == 422
    assert len(client.get(f"/api/wallets/{wallet_id}/operations").json()) == 1


def fund_in_the_past(client: TestClient, wallet_id: str, amount: str) -> None:
    response = client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": amount, "timestamp": "2024-01-02T09:00:00Z"})
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

    response = client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    assert response.status_code == 200
    assert response.json()["cash"] == "90.32"
    assert response.json()["holdings"] == {"NVDA": "8"}
    buy = client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]
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
        f"/api/wallets/{wallet_id}/buys",
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

    response = client.post(f"/api/wallets/{wallet_id}/buys", json={**NVDA_BUY, "settled_amount": None})
    assert response.status_code == 422


def test_buy_before_the_cash_arrived_is_rejected(client: TestClient) -> None:
    # The wallet has enough cash now, but the starting deposit is dated after the buy.
    wallet_id = create_wallet(client, "5000")

    response = client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    assert response.status_code == 422
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {}


def test_past_sell_reduces_holdings_and_adds_settled_amount(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)

    response = client.post(f"/api/wallets/{wallet_id}/sells", json=nvda_sell("5"))
    assert response.status_code == 200
    assert response.json()["cash"] == "688.32"  # 90.32 + 600.00 - 2.00
    assert response.json()["holdings"] == {"NVDA": "3"}


def test_wallet_shows_fifo_cost_and_realized_gain(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)  # 8 NVDA for 907.68 + 2.00 fees

    wallet = client.post(f"/api/wallets/{wallet_id}/sells", json=nvda_sell("5")).json()  # 600.00 - 2.00 fees
    # 5 of 8 shares sold: they cost 5/8 of 909.68 = 568.55; 598.00 - 568.55 = 29.45 gained.
    assert (wallet["cost_basis"], wallet["realized_gain"]) == ({"NVDA": "341.13"}, "29.45")


def test_selling_everything_removes_the_holding(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)

    response = client.post(f"/api/wallets/{wallet_id}/sells", json=nvda_sell("8"))
    assert response.json()["holdings"] == {}


@pytest.mark.parametrize(
    ("quantity", "timestamp"),
    [
        ("9", "2024-07-10T14:00:00Z"),  # more than the 8 held
        ("1", "2024-06-01T14:00:00Z"),  # before the shares were bought
    ],
)
def test_selling_shares_not_held_at_that_time_is_rejected(client: TestClient, quantity: str, timestamp: str) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)

    response = client.post(f"/api/wallets/{wallet_id}/sells", json={**nvda_sell(quantity), "timestamp": timestamp})
    assert response.status_code == 422
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {"NVDA": "8"}


def nvda_sell(quantity: str) -> dict[str, str]:
    return {
        "symbol": "NVDA",
        "quantity": quantity,
        "price": "130",
        "price_currency": "USD",
        "timestamp": "2024-07-10T14:00:00Z",
        "settled_amount": "600.00",
        "fees": "2.00",
    }


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

    response = client.post(f"/api/wallets/{wallet_id}/buys", json={**NVDA_BUY, **change})
    assert response.status_code == 422


def operation_ids(client: TestClient, wallet_id: str) -> list[str]:
    return [op["id"] for op in client.get(f"/api/wallets/{wallet_id}/operations").json()]


def test_editing_an_operation_keeps_its_id_and_recomputes_the_wallet(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    deposit_id = operation_ids(client, wallet_id)[0]

    response = client.put(
        f"/api/wallets/{wallet_id}/operations/{deposit_id}", json={"type": "deposit", "amount": "2000", "timestamp": "2024-01-02T09:00:00Z"}
    )
    assert response.status_code == 200
    assert response.json()["cash"] == "1090.32"  # 2000 - 907.68 - 2.00
    assert operation_ids(client, wallet_id)[0] == deposit_id


def test_editing_cannot_change_the_type(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "30"})
    withdrawal_id = operation_ids(client, wallet_id)[1]

    response = client.put(f"/api/wallets/{wallet_id}/operations/{withdrawal_id}", json={"type": "deposit", "amount": "30"})
    assert response.status_code == 422
    assert response.json()["detail"] == "the type of an operation cannot change; delete it and add a new one"
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "70"


def test_an_edit_that_breaks_the_timeline_is_rejected_and_changes_nothing(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    deposit_id = operation_ids(client, wallet_id)[0]

    # The buy needs 909.68 in June 2024; a 900 deposit is not enough.
    response = client.put(
        f"/api/wallets/{wallet_id}/operations/{deposit_id}", json={"type": "deposit", "amount": "900", "timestamp": "2024-01-02T09:00:00Z"}
    )
    assert response.status_code == 422
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "90.32"


def test_deleting_an_operation_recomputes_the_wallet(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    buy_id = operation_ids(client, wallet_id)[1]

    response = client.delete(f"/api/wallets/{wallet_id}/operations/{buy_id}")
    assert response.status_code == 200
    assert (response.json()["cash"], response.json()["holdings"]) == ("1000", {})
    assert buy_id not in operation_ids(client, wallet_id)


def test_deleting_an_operation_others_depend_on_is_rejected(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)
    deposit_id = operation_ids(client, wallet_id)[0]

    assert client.delete(f"/api/wallets/{wallet_id}/operations/{deposit_id}").status_code == 422
    assert len(operation_ids(client, wallet_id)) == 2


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_unknown_operation_or_wallet_returns_404(client: TestClient, method: str) -> None:
    wallet_id = create_wallet(client, "100")
    body = {"type": "deposit", "amount": "10"}

    unknown_operation = client.request(method, f"/api/wallets/{wallet_id}/operations/{uuid4()}", json=body)
    assert (unknown_operation.status_code, unknown_operation.json()["detail"]) == (404, "operation not found")
    unknown_wallet = client.request(method, f"/api/wallets/{uuid4()}/operations/{uuid4()}", json=body)
    assert (unknown_wallet.status_code, unknown_wallet.json()["detail"]) == (404, "wallet not found")


def test_copy_has_the_same_history_under_a_new_id(client: TestClient) -> None:
    wallet_id = create_wallet(client, "0")
    fund_in_the_past(client, wallet_id, "1000")
    client.post(f"/api/wallets/{wallet_id}/buys", json=NVDA_BUY)

    response = client.post(f"/api/wallets/{wallet_id}/copies", json={"name": "What if"})
    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != wallet_id
    assert (copy["name"], copy["currency"], copy["cash"], copy["holdings"]) == ("What if", "EUR", "90.32", {"NVDA": "8"})
    original_ops = client.get(f"/api/wallets/{wallet_id}/operations").json()
    copy_ops = client.get(f"/api/wallets/{copy['id']}/operations").json()
    assert [(op["type"], op["timestamp"], op["amount"]) for op in copy_ops] == [
        (op["type"], op["timestamp"], op["amount"]) for op in original_ops
    ]
    assert {op["id"] for op in copy_ops}.isdisjoint(op["id"] for op in original_ops)


def test_copy_changes_independently_of_the_original(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")
    copy_id = client.post(f"/api/wallets/{wallet_id}/copies", json={"name": "Copy"}).json()["id"]

    client.post(f"/api/wallets/{copy_id}/deposits", json={"amount": "50"})
    assert client.get(f"/api/wallets/{copy_id}").json()["cash"] == "150"
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "100"


def test_renamed_wallet_keeps_its_history(client: TestClient) -> None:
    wallet_id = create_wallet(client, "100")

    response = client.patch(f"/api/wallets/{wallet_id}", json={"name": "Renamed"})
    assert response.status_code == 200
    wallet = client.get(f"/api/wallets/{wallet_id}").json()
    assert (wallet["name"], wallet["cash"]) == ("Renamed", "100")
    assert len(client.get(f"/api/wallets/{wallet_id}/operations").json()) == 1


@pytest.mark.parametrize(
    ("method", "path"), [("POST", "/api/wallets"), ("PATCH", "/api/wallets/{id}"), ("POST", "/api/wallets/{id}/copies")]
)
@pytest.mark.parametrize("name", ["", "   "])
def test_blank_names_are_rejected(client: TestClient, method: str, path: str, name: str) -> None:
    wallet_id = create_wallet(client, "100")  # named "Long term"

    response = client.request(method, path.format(id=wallet_id), json={"name": name, "currency": "EUR", "cash": "0"})
    assert response.status_code == 422
    assert response.json()["detail"] == "name must not be blank"
    assert [w["name"] for w in client.get("/api/wallets").json()] == ["Long term"]


def test_deleted_wallet_is_gone(client: TestClient) -> None:
    kept, deleted = create_wallet(client, "10"), create_wallet(client, "20")

    assert client.delete(f"/api/wallets/{deleted}").status_code == 204
    assert client.get(f"/api/wallets/{deleted}").status_code == 404
    assert [w["id"] for w in client.get("/api/wallets").json()] == [kept]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/wallets/{id}"),
        ("DELETE", "/api/wallets/{id}"),
        ("PATCH", "/api/wallets/{id}"),
        ("POST", "/api/wallets/{id}/copies"),
        ("GET", "/api/wallets/{id}/operations"),
        ("POST", "/api/wallets/{id}/deposits"),
        ("POST", "/api/wallets/{id}/withdrawals"),
        ("POST", "/api/wallets/{id}/buys"),
        ("POST", "/api/wallets/{id}/sells"),
    ],
)
def test_unknown_wallet_returns_404(client: TestClient, method: str, path: str) -> None:
    body = (
        NVDA_BUY
        if path.endswith(("buys", "sells"))
        else {"name": "Copy"}
        if path.endswith("copies") or method == "PATCH"
        else {"amount": "10"}
    )
    response = client.request(method, path.format(id=uuid4()), json=body)
    assert response.status_code == 404
