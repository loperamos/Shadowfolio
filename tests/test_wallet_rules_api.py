"""The owner's rules for a wallet, checked when an order is placed: the largest share of the wallet one holding may
reach, the share to keep in cash, the symbols it may buy, and how many orders it may place in a month. Each buy counts
at its estimate (see the order estimate), with the open buys already waiting, so splitting an order does not get around
a rule. Sells only lower a holding and raise the cash, so only the monthly limit applies to them."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
NO_RULES: dict[str, Any] = {"max_position_weight": None, "min_cash_weight": None, "allowed_symbols": [], "max_orders_per_month": None}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def client(clock: FixedClock) -> TestClient:
    prices = InMemoryPriceData({"NVDA": Quote(Decimal("100"), Currency.USD, datetime(2026, 3, 2, 14, 59, tzinfo=UTC))})
    return TestClient(build_test_app(clock=clock, prices=prices))


def wallet_with(client: TestClient, **rules: Any) -> str:
    """A USD wallet with 10000 in cash and the given rules."""
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "10000"}).json()["id"]
    response = client.put(f"/api/wallets/{wallet_id}/rules", json={**NO_RULES, **rules})
    assert response.status_code == 200, response.json()
    return wallet_id


def buy(client: TestClient, wallet_id: str, quantity: str, side: str = "buy", symbol: str = "NVDA") -> tuple[int, str]:
    response = client.post(f"/api/wallets/{wallet_id}/orders", json={"side": side, "symbol": symbol, "quantity": quantity})
    return response.status_code, response.json().get("detail", "")


def test_rules_are_kept_with_the_wallet_and_can_be_lifted(client: TestClient) -> None:
    wallet_id = wallet_with(
        client, max_position_weight="0.2", min_cash_weight="0.05", allowed_symbols=["nvda ", "BRK.B", "NVDA"], max_orders_per_month=10
    )
    assert client.get(f"/api/wallets/{wallet_id}").json()["rules"] == {
        "max_position_weight": "0.2",
        "min_cash_weight": "0.05",
        "allowed_symbols": ["NVDA", "BRK.B"],  # as market data writes them, once each
        "max_orders_per_month": 10,
    }

    lifted = client.put(f"/api/wallets/{wallet_id}/rules", json=NO_RULES)

    assert lifted.json()["rules"] == NO_RULES


@pytest.mark.parametrize(
    "rules",
    [
        {"max_position_weight": "0"},
        {"max_position_weight": "1.5"},
        {"min_cash_weight": "-0.1"},
        {"allowed_symbols": ["NVDA", " "]},
        {"max_orders_per_month": 0},
    ],
)
def test_a_rule_out_of_range_is_refused(client: TestClient, rules: dict[str, Any]) -> None:
    wallet_id = wallet_with(client)

    response = client.put(f"/api/wallets/{wallet_id}/rules", json={**NO_RULES, **rules})

    assert response.status_code == 422


def test_a_buy_that_would_make_a_holding_too_large_is_refused(client: TestClient) -> None:
    wallet_id = wallet_with(client, max_position_weight="0.2")

    assert buy(client, wallet_id, "25") == (422, "the order would put 25.00% of the wallet in NVDA, above the limit of 20.00%")
    assert buy(client, wallet_id, "20")[0] == 201  # 2000 of 10000: at the limit
    # That open buy already counts: one more share would make 21%.
    assert buy(client, wallet_id, "1") == (422, "the order would put 21.00% of the wallet in NVDA, above the limit of 20.00%")


def test_a_buy_that_would_leave_too_little_cash_is_refused(client: TestClient) -> None:
    wallet_id = wallet_with(client, min_cash_weight="0.9")

    assert buy(client, wallet_id, "15") == (422, "the order would leave 85.00% of the wallet in cash, below the minimum of 90.00%")
    assert buy(client, wallet_id, "10")[0] == 201


def test_only_the_allowed_symbols_can_be_bought_but_any_sold(client: TestClient) -> None:
    wallet_id = wallet_with(client, allowed_symbols=["NVDA"])

    assert buy(client, wallet_id, "1", symbol="aapl") == (422, "AAPL is not among the symbols this wallet may buy")
    assert buy(client, wallet_id, "1")[0] == 201
    assert buy(client, wallet_id, "1", side="sell", symbol="AAPL")[0] == 201  # getting out of anything is allowed


def test_orders_are_limited_per_calendar_month_not_counting_cancelled_ones(client: TestClient, clock: FixedClock) -> None:
    wallet_id = wallet_with(client, max_orders_per_month=2)
    assert buy(client, wallet_id, "1")[0] == 201
    cancelled = client.post(f"/api/wallets/{wallet_id}/orders", json={"side": "sell", "symbol": "NVDA", "quantity": "1"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/orders/{cancelled}/cancel")

    assert buy(client, wallet_id, "1", side="sell")[0] == 201  # the second, sells included
    assert buy(client, wallet_id, "1") == (422, "the wallet has placed 2 orders this month, its limit")
    clock.set(datetime(2026, 4, 1, 13, 30, tzinfo=UTC))
    assert buy(client, wallet_id, "1")[0] == 201


def test_sells_are_not_refused_for_the_size_of_a_holding_or_the_cash(client: TestClient) -> None:
    wallet_id = wallet_with(client, max_position_weight="0.01", min_cash_weight="0.99")

    assert buy(client, wallet_id, "5", side="sell")[0] == 201  # rejected later if there are no shares to sell, as any


def test_an_unknown_wallet_has_no_rules_to_set(client: TestClient) -> None:
    response = client.put("/api/wallets/00000000-0000-0000-0000-000000000000/rules", json=NO_RULES)

    assert response.status_code == 404
