"""Orders placed now. A market order fills at the first price after it was placed (the next minute bar's open), so
never with hindsight; one placed while the market is closed waits for the next open. A limit order fills on the first
later minute bar that reaches its limit, at the limit or the bar's better open. Orders fill when a wallet's
orders are read, and in a job for every wallet. The clock and the minute bars are set by hand here, as the market's
hours are simulated, not waited for."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.market import MinuteBar
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

MONDAY_TRADING = datetime(2024, 6, 24, 14, 26, 30, tzinfo=UTC)  # half a minute into the 14:26 bar
NEXT_MINUTE = datetime(2024, 6, 24, 14, 27, tzinfo=UTC)
MONDAY_NIGHT = datetime(2024, 6, 24, 23, 0, tzinfo=UTC)
TUESDAY_OPEN = datetime(2024, 6, 25, 13, 30, tzinfo=UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(MONDAY_TRADING)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData()


@pytest.fixture
def client(clock: FixedClock, prices: InMemoryPriceData) -> TestClient:
    return TestClient(build_test_app(clock=clock, prices=prices))


def bar(prices: InMemoryPriceData, at: datetime, price: str) -> None:
    prices.add_bar("NVDA", Quote(Decimal(price), Currency.USD, at))


def funded_wallet(client: TestClient) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "10000", "timestamp": "2024-06-20T09:00:00Z"})
    return wallet_id


def minute(prices: InMemoryPriceData, at: datetime, open_: str, high: str, low: str) -> None:
    prices.add_minute_bar("NVDA", MinuteBar(at, Decimal(open_), Decimal(high), Decimal(low), Currency.USD))


def place(client: TestClient, wallet_id: str, side: str, quantity: str, reason: str = "", limit: str | None = None) -> dict[str, Any]:
    body = {"side": side, "symbol": "NVDA", "quantity": quantity, "reason": reason, "limit_price": limit}
    response = client.post(f"/api/wallets/{wallet_id}/orders", json=body)
    assert response.status_code == 201, response.json()
    order: dict[str, Any] = response.json()
    return order


def orders(client: TestClient, wallet_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get(f"/api/wallets/{wallet_id}/orders").json()
    return result


def test_a_market_order_fills_at_the_next_minutes_open(client: TestClient, clock: FixedClock, prices: InMemoryPriceData) -> None:
    wallet_id = funded_wallet(client)
    bar(prices, datetime(2024, 6, 24, 14, 26, tzinfo=UTC), "120.00")  # started before the order: never used
    bar(prices, NEXT_MINUTE, "121.81")

    placed = place(client, wallet_id, "buy", "8", reason="Breaking out")
    assert (placed["status"], placed["reason"], placed["placed_at"]) == ("open", "Breaking out", "2024-06-24T14:26:30Z")

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))
    [order] = orders(client, wallet_id)

    assert (order["status"], order["closed_at"], order["price"], order["price_currency"]) == (
        "filled",
        "2024-06-24T14:27:00Z",
        "121.81",
        "USD",
    )
    wallet = client.get(f"/api/wallets/{wallet_id}").json()
    assert (wallet["cash"], wallet["holdings"], wallet["hindsight"]) == ("9025.52", {"NVDA": "8"}, False)  # 10000 - 8 x 121.81
    trade = client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]
    assert (trade["type"], trade["timestamp"], trade["price_source"]) == ("buy", "2024-06-24T14:27:00Z", "order")


def test_an_order_placed_while_the_market_is_closed_waits_for_the_next_open(
    client: TestClient, clock: FixedClock, prices: InMemoryPriceData
) -> None:
    wallet_id = funded_wallet(client)
    bar(prices, TUESDAY_OPEN, "118.00")
    clock.set(MONDAY_NIGHT)
    place(client, wallet_id, "buy", "1")

    clock.set(datetime(2024, 6, 25, 9, 0, tzinfo=UTC))
    assert orders(client, wallet_id)[0]["status"] == "open"

    clock.set(datetime(2024, 6, 25, 13, 31, tzinfo=UTC))
    [order] = orders(client, wallet_id)
    assert (order["status"], order["closed_at"], order["price"]) == ("filled", "2024-06-25T13:30:00Z", "118.00")


def test_a_cancelled_order_never_fills(client: TestClient, clock: FixedClock, prices: InMemoryPriceData) -> None:
    wallet_id = funded_wallet(client)
    bar(prices, NEXT_MINUTE, "121.81")
    order_id = place(client, wallet_id, "buy", "8")["id"]

    cancelled = client.post(f"/api/wallets/{wallet_id}/orders/{order_id}/cancel")
    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))

    assert (cancelled.status_code, cancelled.json()["status"]) == (200, "cancelled")
    assert orders(client, wallet_id)[0]["status"] == "cancelled"
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {}
    again = client.post(f"/api/wallets/{wallet_id}/orders/{order_id}/cancel")
    assert (again.status_code, again.json()["detail"]) == (422, "only an open order can be cancelled")


def test_an_order_the_wallet_cannot_afford_is_rejected_with_the_reason(
    client: TestClient, clock: FixedClock, prices: InMemoryPriceData
) -> None:
    wallet_id = funded_wallet(client)
    bar(prices, NEXT_MINUTE, "121.81")
    place(client, wallet_id, "buy", "100")  # 12,181 USD, with 10,000 in cash
    place(client, wallet_id, "sell", "1")  # nothing held

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))
    statuses = [(order["side"], order["status"], order["rejection"]) for order in orders(client, wallet_id)]

    assert statuses == [
        ("buy", "rejected", "cash would be -2181.00 on 2024-06-24T14:27:00+00:00"),
        ("sell", "rejected", "would hold -1 NVDA on 2024-06-24T14:27:00+00:00"),
    ]
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "10000"


def test_the_job_fills_every_wallets_due_orders(client: TestClient, clock: FixedClock, prices: InMemoryPriceData) -> None:
    first, second = funded_wallet(client), funded_wallet(client)
    bar(prices, NEXT_MINUTE, "121.81")
    place(client, first, "buy", "1")
    place(client, second, "buy", "2")

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))
    response = client.post("/api/orders/fill")

    assert (response.status_code, response.json()) == (200, {"wallets": 2, "filled": 2})
    assert client.get(f"/api/wallets/{second}").json()["holdings"] == {"NVDA": "2"}


def test_a_limit_buy_fills_on_the_first_later_bar_that_reaches_its_limit(
    client: TestClient, clock: FixedClock, prices: InMemoryPriceData
) -> None:
    wallet_id = funded_wallet(client)
    minute(prices, NEXT_MINUTE, "121.00", "122.00", "120.50")  # never down to 120
    minute(prices, datetime(2024, 6, 24, 14, 28, tzinfo=UTC), "121.00", "121.00", "119.50")
    placed = place(client, wallet_id, "buy", "8", limit="120")
    assert (placed["status"], placed["limit_price"]) == ("open", "120")

    clock.set(datetime(2024, 6, 24, 14, 27, 30, tzinfo=UTC))  # the 14:28 bar has not happened yet
    assert orders(client, wallet_id)[0]["status"] == "open"

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))
    [order] = orders(client, wallet_id)
    # The bar opened above the limit and came down to it: filled at the limit, not at a lower price seen later.
    assert (order["status"], order["closed_at"], order["price"]) == ("filled", "2024-06-24T14:28:00Z", "120")


def test_a_limit_buy_fills_at_the_open_when_a_bar_opens_better_than_the_limit(
    client: TestClient, clock: FixedClock, prices: InMemoryPriceData
) -> None:
    wallet_id = funded_wallet(client)
    minute(prices, NEXT_MINUTE, "118.00", "119.00", "117.00")
    place(client, wallet_id, "buy", "8", limit="120")

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))

    assert orders(client, wallet_id)[0]["price"] == "118.00"


def test_a_limit_sell_fills_when_a_later_bar_rises_to_its_limit(client: TestClient, clock: FixedClock, prices: InMemoryPriceData) -> None:
    wallet_id = funded_wallet(client)
    past_buy = {"symbol": "NVDA", "quantity": "2", "price": "100", "price_currency": "USD", "timestamp": "2024-06-21T15:00:00Z"}
    assert client.post(f"/api/wallets/{wallet_id}/buys", json=past_buy).status_code == 200
    minute(prices, NEXT_MINUTE, "129.00", "131.00", "128.00")
    place(client, wallet_id, "sell", "2", limit="130")

    clock.set(datetime(2024, 6, 24, 14, 30, tzinfo=UTC))
    [order] = orders(client, wallet_id)

    assert (order["status"], order["price"]) == ("filled", "130")
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {}


def test_a_limit_order_that_is_never_reached_stays_open(client: TestClient, clock: FixedClock, prices: InMemoryPriceData) -> None:
    wallet_id = funded_wallet(client)
    minute(prices, NEXT_MINUTE, "121.00", "122.00", "120.50")
    place(client, wallet_id, "buy", "8", limit="100")

    clock.set(datetime(2024, 6, 25, 20, 0, tzinfo=UTC))

    assert orders(client, wallet_id)[0]["status"] == "open"


@pytest.mark.parametrize(("side", "quantity", "limit"), [("buy", "0", None), ("sell", "-1", None), ("hold", "1", None), ("buy", "1", "0")])
def test_an_invalid_order_is_refused(client: TestClient, side: str, quantity: str, limit: str | None) -> None:
    wallet_id = funded_wallet(client)

    body = {"side": side, "symbol": "NVDA", "quantity": quantity, "limit_price": limit}
    response = client.post(f"/api/wallets/{wallet_id}/orders", json=body)

    assert response.status_code == 422
    assert client.get(f"/api/wallets/{wallet_id}/orders").json() == []
