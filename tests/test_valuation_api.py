from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
QUOTE_TIME = datetime(2026, 3, 2, 14, 59, tzinfo=UTC)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData()


@pytest.fixture
def client(prices: InMemoryPriceData) -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), prices=prices))


def wallet_holding(client: TestClient, *trades: dict[str, str]) -> str:
    """An EUR wallet funded with 3000 EUR in 2024, then the given past buys."""
    wallet_id: str = client.post("/wallets", json={"name": "W", "currency": "EUR", "cash": "0"}).json()["id"]
    client.post(f"/wallets/{wallet_id}/deposits", json={"amount": "3000", "timestamp": "2024-01-02T09:00:00Z"})
    for trade in trades:
        assert client.post(f"/wallets/{wallet_id}/buys", json=trade).status_code == 200
    return wallet_id


NVDA_BUY = {
    "symbol": "NVDA",
    "quantity": "8",
    "price": "121.81",
    "price_currency": "USD",
    "timestamp": "2024-06-24T14:26:00Z",
    "settled_amount": "907.68",
    "fees": "2.00",
}
TSLA_BUY = {
    "symbol": "TSLA",
    "quantity": "5",
    "price": "295.05",
    "price_currency": "EUR",
    "timestamp": "2024-11-15T13:39:00Z",
    "fees": "3.90",
}


def test_cash_only_wallet_is_worth_its_cash(client: TestClient) -> None:
    wallet_id = wallet_holding(client)

    response = client.get(f"/wallets/{wallet_id}/valuation")
    assert response.status_code == 200
    assert response.json() == {"holdings": [], "totals": {"EUR": "3000"}}


def test_holdings_are_valued_at_latest_prices_and_totalled_per_currency(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY, TSLA_BUY)  # cash left: 3000 - 909.68 - 1479.15 = 611.17 EUR
    prices.set("NVDA", Quote(Decimal("135.50"), Currency.USD, QUOTE_TIME))
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME))

    valuation = client.get(f"/wallets/{wallet_id}/valuation").json()
    assert [(h["symbol"], h["quantity"], h["price"], h["currency"], h["value"]) for h in valuation["holdings"]] == [
        ("NVDA", "8", "135.50", "USD", "1084.00"),
        ("TSLA", "5", "310.00", "EUR", "1550.00"),
    ]
    assert valuation["holdings"][0]["as_of"] == "2026-03-02T14:59:00Z"
    # USD is not converted into EUR yet: each currency has its own total.
    assert valuation["totals"] == {"EUR": "2161.17", "USD": "1084.00"}


def test_missing_price_fails_the_valuation(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY, TSLA_BUY)
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME))

    response = client.get(f"/wallets/{wallet_id}/valuation")
    assert response.status_code == 422
    assert response.json()["detail"] == "no price for NVDA"


def test_unknown_wallet_valuation_returns_404(client: TestClient) -> None:
    assert client.get(f"/wallets/{uuid4()}/valuation").status_code == 404
