"""Past trades without a price are priced from market data, and marked as built with hindsight."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
TRADE_TIME = "2024-06-24T14:26:00Z"


@pytest.fixture
def prices() -> InMemoryPriceData:
    prices = InMemoryPriceData()
    # Minute bars around the trade: only the first one at or after its time may be used.
    for minute, open_price in ((25, "121.50"), (27, "122.005"), (28, "122.40")):
        prices.add_bar("NVDA", Quote(Decimal(open_price), Currency.USD, datetime(2024, 6, 24, 14, minute, tzinfo=UTC)))
    return prices


@pytest.fixture
def fx_rates() -> InMemoryFxRates:
    return InMemoryFxRates(FxRate(Currency.USD, Currency.EUR, Decimal("0.9343"), date(2024, 6, 24)))


@pytest.fixture
def client(prices: InMemoryPriceData, fx_rates: InMemoryFxRates) -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=fx_rates))


def funded_wallet(client: TestClient, currency: str) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": currency, "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "5000", "timestamp": "2024-01-02T09:00:00Z"})
    return wallet_id


def test_a_buy_without_a_price_uses_the_first_price_at_or_after_its_time(client: TestClient) -> None:
    wallet_id = funded_wallet(client, "USD")

    response = client.post(f"/api/wallets/{wallet_id}/buys", json={"symbol": "NVDA", "quantity": "8", "timestamp": TRADE_TIME})
    assert response.status_code == 200
    buy = client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]
    # The 14:27 bar's open, never the earlier 14:25 one; the trade keeps its own time.
    assert (buy["price"], buy["price_currency"], buy["amount"], buy["timestamp"]) == ("122.005", "USD", "976.04", TRADE_TIME)
    assert buy["price_source"] == "market"
    assert response.json()["hindsight"] is True


def test_a_market_priced_buy_in_another_currency_settles_at_that_days_rate(client: TestClient) -> None:
    wallet_id = funded_wallet(client, "EUR")

    client.post(f"/api/wallets/{wallet_id}/buys", json={"symbol": "NVDA", "quantity": "8", "timestamp": TRADE_TIME, "fees": "2.00"})
    buy = client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]
    # 8 x 122.005 USD = 976.04 USD; x 0.9343 = 911.91 EUR.
    assert (buy["amount"], buy["fees"]) == ("911.91", "2.00")
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "4086.09"


def test_trades_with_the_brokers_price_are_not_hindsight(client: TestClient) -> None:
    wallet_id = funded_wallet(client, "USD")
    body = {"symbol": "NVDA", "quantity": "8", "timestamp": TRADE_TIME, "price": "121.81", "price_currency": "USD"}

    wallet = client.post(f"/api/wallets/{wallet_id}/buys", json=body).json()
    assert wallet["hindsight"] is False
    assert client.get(f"/api/wallets/{wallet_id}/operations").json()[-1]["price_source"] == "entered"


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"symbol": "AAPL", "quantity": "1", "timestamp": TRADE_TIME}, "no market price for AAPL at or after 2024-06-24T14:26:00+00:00"),
        (
            {"symbol": "NVDA", "quantity": "1", "timestamp": "2024-06-24T14:29:00Z"},
            "no market price for NVDA at or after 2024-06-24T14:29:00+00:00",
        ),
        ({"symbol": "NVDA", "quantity": "1", "timestamp": TRADE_TIME, "price": "120"}, "a price needs its currency"),
    ],
)
def test_trades_that_cannot_be_priced_are_rejected(client: TestClient, body: dict[str, str], detail: str) -> None:
    wallet_id = funded_wallet(client, "USD")

    response = client.post(f"/api/wallets/{wallet_id}/buys", json=body)
    assert (response.status_code, response.json()["detail"]) == (422, detail)


def test_a_market_priced_buy_without_a_rate_for_that_day_is_rejected(prices: InMemoryPriceData) -> None:
    # The price exists, but no USD→EUR rate was published on or before that day.
    client = TestClient(build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=InMemoryFxRates()))
    wallet_id = funded_wallet(client, "EUR")

    response = client.post(f"/api/wallets/{wallet_id}/buys", json={"symbol": "NVDA", "quantity": "1", "timestamp": TRADE_TIME})
    assert (response.status_code, response.json()["detail"]) == (422, "no USD→EUR rate for 2024-06-24")
