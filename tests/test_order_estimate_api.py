"""What an order would come to, before placing it: at its limit price, or at the latest price for a market order, in the
wallet's currency at the latest exchange rate; as the buying power counts it."""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)


def client_and_wallet() -> tuple[TestClient, str]:
    prices = InMemoryPriceData({"NVDA": Quote(Decimal("135.50"), Currency.USD, datetime(2026, 3, 2, 14, 59, tzinfo=UTC))})
    fx_rates = InMemoryFxRates()
    fx_rates.set(FxRate(Currency.USD, Currency.EUR, Decimal("0.9025"), date(2026, 3, 2)))
    client = TestClient(build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=fx_rates))
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "EUR", "cash": "1000"}).json()["id"]
    return client, wallet_id


def estimate(client: TestClient, wallet_id: str, **params: str) -> tuple[int, dict[str, object]]:
    response = client.get(f"/api/wallets/{wallet_id}/orders/estimate", params={"side": "buy", "symbol": "nvda", **params})
    return response.status_code, response.json()


def test_a_market_order_is_estimated_at_the_latest_price() -> None:
    client, wallet_id = client_and_wallet()

    status, result = estimate(client, wallet_id, quantity="3")

    # 3 x 135.50 USD = 406.50 USD, at 0.9025: 366.87 EUR.
    assert status == 200
    assert result == {"price": "135.50", "currency": "USD", "fx_rate": {"rate": "0.9025", "as_of": "2026-03-02"}, "amount": "366.87"}


def test_a_limit_order_is_estimated_at_its_limit() -> None:
    client, wallet_id = client_and_wallet()

    status, result = estimate(client, wallet_id, quantity="2", limit_price="130")

    assert (status, result["price"], result["amount"]) == (200, "130", "234.65")  # 260 USD at 0.9025


def test_an_order_without_a_price_or_with_a_bad_quantity_cannot_be_estimated() -> None:
    client, wallet_id = client_and_wallet()

    assert estimate(client, wallet_id, symbol="ZZZZ", quantity="1")[0] == 422
    assert estimate(client, wallet_id, quantity="0")[0] == 422
    assert (
        client.get(
            "/api/wallets/00000000-0000-0000-0000-000000000000/orders/estimate", params={"side": "buy", "symbol": "NVDA", "quantity": "1"}
        ).status_code
        == 404
    )
