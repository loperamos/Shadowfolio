"""Splits are applied automatically: before a trade is checked, and by the daily sync.

Each wallet records per symbol the period whose splits have been applied; trades are only accepted inside it.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.domain.corporate_actions import SplitEvent
from shadowfolio.ports.corporate_actions import CorporateActionsUnavailableError
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
NVDA_SPLIT = SplitEvent("NVDA", date(2024, 6, 10), Decimal(1), Decimal(10), "nvda-2024-split")


class CountingCorporateActions(InMemoryCorporateActions):
    """The fake, also counting provider calls and able to be made unreachable."""

    def __init__(self, *splits: SplitEvent) -> None:
        super().__init__(*splits)
        self.calls: list[tuple[str, date, date]] = []
        self.unreachable = False

    def splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        self.calls.append((symbol, start, end))
        if self.unreachable:
            raise CorporateActionsUnavailableError("down")
        return super().splits(symbol, start, end)


@pytest.fixture
def actions() -> CountingCorporateActions:
    return CountingCorporateActions(NVDA_SPLIT)


@pytest.fixture
def client(actions: CountingCorporateActions) -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), corporate_actions=actions))


def new_wallet(client: TestClient) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "10000", "timestamp": "2024-01-02T09:00:00Z"})
    return wallet_id


def trade(client: TestClient, wallet_id: str, kind: str, quantity: str, timestamp: str, price: str = "900") -> dict[str, Any]:
    body = {"symbol": "NVDA", "quantity": quantity, "price": price, "price_currency": "USD", "timestamp": timestamp}
    response = client.post(f"/api/wallets/{wallet_id}/{kind}", json=body)
    return {"status": response.status_code, **response.json()}


def test_a_trade_before_a_split_gets_the_split_applied_automatically(client: TestClient) -> None:
    wallet_id = new_wallet(client)

    wallet = trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    assert (wallet["holdings"], wallet["cost_basis"]) == ({"NVDA": "80"}, {"NVDA": "7200.00"})
    split = client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]
    assert (split["type"], split["split_old_rate"], split["split_new_rate"], split["automatic"]) == ("split", "1", "10", True)
    assert wallet["splits_checked_through"] == "2026-03-02"


def test_selling_the_split_shares_works_straight_away(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")

    assert trade(client, wallet_id, "sells", "80", "2024-07-01T15:00:00Z", price="120")["holdings"] == {}


def test_the_provider_is_only_asked_for_days_outside_the_checked_period(client: TestClient, actions: CountingCorporateActions) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    trade(client, wallet_id, "buys", "1", "2024-08-01T15:00:00Z", price="120")  # inside: checked through today
    assert len(actions.calls) == 1

    trade(client, wallet_id, "buys", "1", "2024-03-01T15:00:00Z")  # before the period: checked again from that day
    assert actions.calls[-1] == ("NVDA", date(2024, 3, 1), date(2026, 3, 2))
    assert len(actions.calls) == 2


def test_a_trade_is_refused_and_nothing_changes_when_corporate_actions_cannot_be_checked(
    client: TestClient, actions: CountingCorporateActions
) -> None:
    wallet_id = new_wallet(client)
    actions.unreachable = True

    response = client.post(
        f"/api/wallets/{wallet_id}/buys",
        json={"symbol": "NVDA", "quantity": "8", "price": "900", "price_currency": "USD", "timestamp": "2024-05-01T15:00:00Z"},
    )
    assert (response.status_code, response.json()["detail"]) == (
        422,
        "could not check corporate actions of NVDA right now; try again later",
    )
    wallet = client.get(f"/api/wallets/{wallet_id}").json()
    assert (wallet["holdings"], wallet["splits_checked_through"]) == ({}, None)


def test_the_daily_sync_applies_splits_published_since_and_late_ones(actions: CountingCorporateActions) -> None:
    clock = FixedClock(datetime(2024, 6, 1, 12, 0, tzinfo=UTC))  # before the split
    client = TestClient(build_test_app(clock=clock, corporate_actions=actions))
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {"NVDA": "8"}

    clock.set(datetime(2024, 6, 11, 12, 0, tzinfo=UTC))  # the day after the split
    summary = client.post("/api/sync").json()
    assert summary == {"wallets": 1, "added": 1}
    wallet = client.get(f"/api/wallets/{wallet_id}").json()
    assert (wallet["holdings"], wallet["splits_checked_through"]) == ({"NVDA": "80"}, "2024-06-11")
    # The run looked back a week before the last checked day, for actions published late.
    assert actions.calls[-1] == ("NVDA", date(2024, 5, 25), date(2024, 6, 11))
    assert client.post("/api/sync").json() == {"wallets": 1, "added": 0}


def test_a_split_while_no_shares_are_held_changes_nothing(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    wallet = trade(client, wallet_id, "sells", "80", "2024-07-01T15:00:00Z", price="120")
    trade(client, wallet_id, "buys", "5", "2024-08-01T15:00:00Z", price="120")

    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {"NVDA": "5"}
    assert wallet["status"] == 200


def test_splits_cannot_be_edited_or_deleted(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    split_id = next(op["id"] for op in client.get(f"/api/wallets/{wallet_id}/operations").json() if op["type"] == "split")

    deleted = client.delete(f"/api/wallets/{wallet_id}/operations/{split_id}")
    edited = client.put(f"/api/wallets/{wallet_id}/operations/{split_id}", json={"type": "deposit", "amount": "1"})
    assert (deleted.status_code, deleted.json()["detail"]) == (422, "operations added from market data (e.g. splits) cannot be deleted")
    assert (edited.status_code, edited.json()["detail"]) == (422, "operations added from market data (e.g. splits) cannot be edited")


def test_the_daily_sync_also_checks_trades_recorded_before_periods_existed(actions: CountingCorporateActions) -> None:
    repository = InMemoryWalletRepository()
    client = TestClient(build_test_app(clock=FixedClock(NOW), corporate_actions=actions, wallet_repository=repository))
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    # Store it as it was before checked periods existed: the trade, without the split or a period for NVDA.
    stored = repository.get(UUID(wallet_id))
    assert stored is not None
    repository.update(replace(stored, operations=tuple(op for op in stored.operations if not op.automatic), checked={}))

    assert client.post("/api/sync").json() == {"wallets": 1, "added": 1}
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {"NVDA": "80"}


def operations_of(client: TestClient, wallet_id: str) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = client.get(f"/api/wallets/{wallet_id}/operations").json()
    return operations


def test_removing_the_last_trade_of_a_symbol_removes_its_splits_and_checked_period(
    client: TestClient, actions: CountingCorporateActions
) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    buy_id = next(op["id"] for op in operations_of(client, wallet_id) if op["type"] == "buy")

    wallet = client.delete(f"/api/wallets/{wallet_id}/operations/{buy_id}").json()
    assert [op["type"] for op in operations_of(client, wallet_id)] == ["deposit"]
    assert (wallet["holdings"], wallet["splits_checked_through"]) == ({}, None)

    # Trading it again checks its splits again.
    calls_before = len(actions.calls)
    assert trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")["holdings"] == {"NVDA": "80"}
    assert len(actions.calls) == calls_before + 1


def test_editing_the_last_trade_into_another_symbol_cleans_up_the_old_one(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    buy_id = next(op["id"] for op in operations_of(client, wallet_id) if op["type"] == "buy")
    body = {"type": "buy", "symbol": "AAPL", "quantity": "8", "price": "170", "price_currency": "USD", "timestamp": "2024-05-01T15:00:00Z"}

    assert client.put(f"/api/wallets/{wallet_id}/operations/{buy_id}", json=body).json()["holdings"] == {"AAPL": "8"}
    assert [(op["type"], op["symbol"]) for op in operations_of(client, wallet_id)] == [("deposit", None), ("buy", "AAPL")]


def test_a_split_when_no_shares_were_held_is_marked_as_without_effect(client: TestClient) -> None:
    wallet_id = new_wallet(client)
    trade(client, wallet_id, "buys", "8", "2024-05-01T15:00:00Z")
    trade(client, wallet_id, "sells", "8", "2024-05-20T15:00:00Z")  # sold before the split
    trade(client, wallet_id, "buys", "5", "2024-08-01T15:00:00Z", price="120")

    split = next(op for op in operations_of(client, wallet_id) if op["type"] == "split")
    assert split["had_effect"] is False
