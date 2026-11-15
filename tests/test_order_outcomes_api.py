"""How each filled order turned out: the symbol's return from its fill price to its latest, next to the benchmark's
over the same time, as a decision log to learn from (e.g. selling winners too early, keeping losers too long). Each
in its own currency: a return compares decisions whatever the currency."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

PLACED = datetime(2024, 6, 24, 14, 26, 30, tzinfo=UTC)
FILLED = datetime(2024, 6, 24, 14, 27, tzinfo=UTC)
LATER = datetime(2024, 7, 24, 15, 0, tzinfo=UTC)


def test_a_filled_order_comes_with_its_return_since_and_the_benchmarks() -> None:
    clock = FixedClock(PLACED)
    prices = InMemoryPriceData()
    client = TestClient(build_test_app(clock=clock, prices=prices))
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "10000"}).json()["id"]
    for symbol, price in [("NVDA", "121.81"), ("SPY", "540.00")]:
        prices.add_bar(symbol, Quote(Decimal(price), Currency.USD, FILLED))
    filled = client.post(f"/api/wallets/{wallet_id}/orders", json={"side": "buy", "symbol": "NVDA", "quantity": "8", "reason": "Breakout"})
    still_open = client.post(
        f"/api/wallets/{wallet_id}/orders", json={"side": "buy", "symbol": "NVDA", "quantity": "1", "limit_price": "50"}
    )
    clock.set(LATER)
    prices.set("NVDA", Quote(Decimal("134.00"), Currency.USD, LATER))
    prices.set("SPY", Quote(Decimal("550.00"), Currency.USD, LATER))
    client.get(f"/api/wallets/{wallet_id}/orders")  # fills the market order

    outcomes = client.get(f"/api/wallets/{wallet_id}/orders/outcomes").json()

    # NVDA 121.81 to 134.00 is +10.01%; SPY from 540 at the same minute to 550, +1.85%. The open order has none yet.
    assert outcomes == [
        {
            "order_id": filled.json()["id"],
            "price": "134.00",
            "currency": "USD",
            "as_of": "2024-07-24T15:00:00Z",
            "return_percent": "10.01",
            "benchmark_symbol": "SPY",
            "benchmark_return_percent": "1.85",
        }
    ]
    assert still_open.json()["id"] not in {outcome["order_id"] for outcome in outcomes}

    # Another benchmark; one without prices leaves its return unknown, not the order's.
    [other] = client.get(f"/api/wallets/{wallet_id}/orders/outcomes", params={"benchmark": "qqq"}).json()
    assert (other["benchmark_symbol"], other["return_percent"], other["benchmark_return_percent"]) == ("QQQ", "10.01", None)


def test_an_unknown_wallet_has_no_outcomes() -> None:
    client = TestClient(build_test_app(prices=InMemoryPriceData()))

    assert client.get("/api/wallets/00000000-0000-0000-0000-000000000000/orders/outcomes").status_code == 404
