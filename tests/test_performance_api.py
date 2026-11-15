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


def test_the_daily_returns_from_zero_come_with_the_performance(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "1000", "timestamp": "2024-06-03T09:00:00Z"})
    spy_close(prices, MONDAY, "500")
    spy_close(prices, TUESDAY, "550")

    result = client.get(f"/api/wallets/{wallet_id}/performance", params={"start": "2024-06-04"}).json()

    # From the end of Monday: the wallet held cash only; SPY rose 10% on Tuesday and kept that close on Wednesday.
    assert [(r["day"], r["value"]) for r in result["wallet_returns"]] == [
        ("2024-06-03", "0.00"),
        ("2024-06-04", "0.00"),
        ("2024-06-05", "0.00"),
    ]
    assert [(r["day"], r["value"]) for r in result["benchmark_returns"]] == [
        ("2024-06-03", "0.00"),
        ("2024-06-04", "10.00"),
        ("2024-06-05", "10.00"),
    ]


def test_a_period_says_how_much_was_traded_and_paid_in_fees(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "10000", "timestamp": "2024-06-01T09:00:00Z"})
    trade = {"symbol": "AAPL", "price_currency": "USD"}
    for kind, day, quantity, price, fees in [
        ("buys", "2024-06-01", "5", "100", "1"),  # before the period: not counted
        ("buys", "2024-06-03", "10", "100", "2"),
        ("sells", "2024-06-04", "5", "110", "2"),
    ]:
        body = {**trade, "quantity": quantity, "price": price, "fees": fees, "timestamp": f"{day}T14:00:00Z"}
        assert client.post(f"/api/wallets/{wallet_id}/{kind}", json=body).status_code == 200
    closes: list[tuple[date, str]] = [(MONDAY, "100"), (TUESDAY, "110")]
    for close_day, close in closes:
        at = datetime(close_day.year, close_day.month, close_day.day, 20, 0, tzinfo=UTC)
        prices.add_close("AAPL", Quote(Decimal(close), Currency.USD, at))

    response = client.get(f"/api/wallets/{wallet_id}/performance", params={"start": "2024-06-03", "end": "2024-06-04"})

    # Worth 8497 + 15 x 100 = 9997 on Monday and 9045 + 10 x 110 = 10145 on Tuesday: 10071 on average. Turnover is the
    # smaller of buys and sells against it, 550 / 10071; fees 4 / 10071.
    assert response.json()["trading"] == {
        "bought": "1000.00",
        "sold": "550.00",
        "fees": "4.00",
        "turnover_percent": "5.46",
        "fees_percent": "0.04",
    }


def test_each_holding_says_how_much_of_the_gain_it_brought(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "USD", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "10000", "timestamp": "2024-06-01T09:00:00Z"})
    for kind, day, symbol, quantity, price in [
        ("buys", "2024-06-03", "AAPL", "10", "100"),
        ("buys", "2024-06-03", "MSFT", "4", "50"),
        ("sells", "2024-06-04", "MSFT", "4", "55"),  # sold out in the period: still part of what drove it
    ]:
        body = {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "price_currency": "USD",
            "fees": "1",
            "timestamp": f"{day}T14:00:00Z",
        }
        assert client.post(f"/api/wallets/{wallet_id}/{kind}", json=body).status_code == 200
    closes: list[tuple[str, date, str]] = [
        ("AAPL", MONDAY, "100"),
        ("AAPL", TUESDAY, "104"),
        ("MSFT", MONDAY, "50"),
        ("MSFT", TUESDAY, "55"),
    ]
    for symbol, close_day, close in closes:
        at = datetime(close_day.year, close_day.month, close_day.day, 20, 0, tzinfo=UTC)
        prices.add_close(symbol, Quote(Decimal(close), Currency.USD, at))

    result = client.get(f"/api/wallets/{wallet_id}/performance", params={"start": "2024-06-04", "end": "2024-06-04"}).json()

    # From Monday's end: AAPL 1000 to 1040; MSFT 200, sold for 220 less a fee of 1. Together the wallet's gain of 59, on
    # an average value of 10057.
    assert result["wallet"]["gain"] == "59.00"
    assert [(c["symbol"], c["start_value"], c["end_value"], c["gain"], c["gain_percent"]) for c in result["contributions"]] == [
        ("AAPL", "1000.00", "1040.00", "40.00", "0.40"),
        ("MSFT", "200.00", "0.00", "19.00", "0.19"),
    ]
    assert result["other_gain"] == "0.00"  # nothing outside the holdings, e.g. fees charged on their own
