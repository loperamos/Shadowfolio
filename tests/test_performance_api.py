"""How a wallet did over a period, next to SPY with the same deposits: gain and returns (see domain.performance)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2024, 6, 5, 15, 0, tzinfo=UTC)
MONDAY, TUESDAY = date(2024, 6, 3), date(2024, 6, 4)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData()


@pytest.fixture
def client(prices: InMemoryPriceData) -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), prices=prices))


def spy_close(prices: InMemoryPriceData, day: date, price: str) -> None:
    prices.add_close("SPY", Quote(Decimal(price), Currency.USD, datetime(day.year, day.month, day.day, 4, 0, tzinfo=UTC)))


def test_a_period_compares_the_wallet_with_spy(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "1000", "timestamp": "2024-06-03T09:00:00Z"})
    spy_close(prices, MONDAY, "500")
    spy_close(prices, TUESDAY, "550")

    response = client.get(f"/api/wallets/{wallet_id}/performance", params={"start": "2024-06-04", "end": "2024-06-04"})

    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    fields = ("start_day", "end_day", "start_value", "end_value", "net_deposits", "gain", "time_weighted_return")
    # The wallet held cash only; SPY with the same 1000 rose 10% on Tuesday.
    assert [result["wallet"][field] for field in fields] == ["2024-06-03", "2024-06-04", "1000.00", "1000.00", "0.00", "0.00", "0.00"]
    assert result["benchmark_symbol"] == "SPY"
    assert [result["benchmark"][field] for field in fields] == ["2024-06-03", "2024-06-04", "1000.00", "1100.00", "0.00", "100.00", "10.00"]
    assert result["wallet"]["time_weighted_return_per_year"] is None  # a period shorter than a year


def test_an_unknown_wallet_has_no_performance(client: TestClient) -> None:
    assert client.get("/api/wallets/00000000-0000-0000-0000-000000000000/performance").status_code == 404


def test_the_benchmark_can_be_another_symbol_or_have_no_prices(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "1000", "timestamp": "2024-06-03T09:00:00Z"})
    prices.add_close("QQQ", Quote(Decimal("400"), Currency.USD, datetime(2024, 6, 3, 4, 0, tzinfo=UTC)))
    prices.add_close("QQQ", Quote(Decimal("380"), Currency.USD, datetime(2024, 6, 4, 4, 0, tzinfo=UTC)))
    period = {"start": "2024-06-04", "end": "2024-06-04"}

    qqq = client.get(f"/api/wallets/{wallet_id}/performance", params={**period, "symbol": "QQQ"}).json()
    unknown = client.get(f"/api/wallets/{wallet_id}/performance", params={**period, "symbol": "ZZZZ"}).json()

    assert (qqq["benchmark_symbol"], qqq["benchmark"]["time_weighted_return"]) == ("QQQ", "-5.00")
    # Without prices there is nothing to compare with; the wallet's own numbers are still there.
    assert (unknown["benchmark_symbol"], unknown["benchmark"], unknown["wallet"]["gain"]) == ("ZZZZ", None, "0.00")
