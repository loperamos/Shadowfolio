"""Copying a wallet at a time: its history up to then, to change from there ("what if").

The copy drops what the owner did from that time on; what happens to the shares anyway (splits, dividends worked out
from what the copy holds) still happens.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.domain.corporate_actions import DividendEvent, SplitEvent
from shadowfolio.domain.money import Currency
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
NVDA_SPLIT = SplitEvent("NVDA", date(2024, 6, 10), Decimal(1), Decimal(10), "nvda-2024-split")
GOOGL_DIVIDEND = DividendEvent("GOOGL", date(2024, 6, 10), date(2024, 6, 17), Decimal("0.20"), Currency.USD, "googl-2024-06")
CUT_OFF = "2024-06-01T00:00:00Z"


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), corporate_actions=InMemoryCorporateActions(NVDA_SPLIT, GOOGL_DIVIDEND)))


def new_wallet(client: TestClient) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "Real", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "10000", "timestamp": "2024-01-02T09:00:00Z"})
    return wallet_id


def trade(client: TestClient, wallet_id: str, kind: str, symbol: str, quantity: str, timestamp: str, price: str) -> None:
    body = {"symbol": symbol, "quantity": quantity, "price": price, "price_currency": "USD", "timestamp": timestamp}
    assert client.post(f"/api/wallets/{wallet_id}/{kind}", json=body).status_code == 200


def copy_before(client: TestClient, wallet_id: str, before: str) -> dict[str, Any]:
    response = client.post(f"/api/wallets/{wallet_id}/copies", json={"name": "What if", "before": before})
    assert response.status_code == 201, response.json()
    copy: dict[str, Any] = response.json()
    return copy


def test_a_copy_at_a_time_has_the_history_before_it(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "500", "timestamp": "2024-07-01T09:00:00Z"})

    copy = copy_before(client, wallet_id, CUT_OFF)

    assert (copy["name"], copy["cash"]) == ("What if", "10000")
    operations = client.get(f"/api/wallets/{copy['id']}/operations").json()
    assert [(op["type"], op["timestamp"]) for op in operations] == [("deposit", "2024-01-02T09:00:00Z")]
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "9500"  # the original is unchanged


def test_splits_after_the_time_still_apply_to_the_copy(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "NVDA", "8", "2024-05-01T15:00:00Z", "900")
    trade(client, wallet_id, "sells", "NVDA", "80", "2024-07-01T15:00:00Z", "120")

    copy = copy_before(client, wallet_id, CUT_OFF)

    # The sale is the owner's and is dropped; the split happens anyway: the copy still holds the 80 shares.
    assert copy["holdings"] == {"NVDA": "80"}
    operations = client.get(f"/api/wallets/{copy['id']}/operations").json()
    assert [op["type"] for op in operations] == ["deposit", "buy", "split"]


def test_dividends_after_the_time_follow_what_the_copy_holds(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "GOOGL", "10", "2024-05-01T15:00:00Z", "170")
    trade(client, wallet_id, "sells", "GOOGL", "10", "2024-06-05T15:00:00Z", "175")  # before the ex-date: no dividend

    copy = copy_before(client, wallet_id, CUT_OFF)

    operations = client.get(f"/api/wallets/{copy['id']}/operations").json()
    assert [(op["type"], op["amount"]) for op in operations if op["type"] == "dividend"] == [("dividend", "2.00")]  # 10 x 0.20


def test_a_copy_without_a_time_has_the_whole_history(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "500", "timestamp": "2024-07-01T09:00:00Z"})

    copy = client.post(f"/api/wallets/{wallet_id}/copies", json={"name": "Copy"}).json()

    assert copy["cash"] == "9500"
