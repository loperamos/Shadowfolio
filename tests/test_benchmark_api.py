"""A benchmark with the same deposits: what the wallet's money would be worth had every deposit bought SPY that day,
and every withdrawal sold the same share of it as it took from the wallet, with SPY's dividends reinvested after the
wallet's withholding tax."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2024, 6, 7, 15, 0, tzinfo=UTC)
MONDAY, TUESDAY, WEDNESDAY, THURSDAY = date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5), date(2024, 6, 6)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData()


@pytest.fixture
def actions() -> InMemoryCorporateActions:
    return InMemoryCorporateActions()


@pytest.fixture
def client(prices: InMemoryPriceData, actions: InMemoryCorporateActions) -> TestClient:
    fx_rates = InMemoryFxRates(FxRate(Currency.USD, Currency.EUR, Decimal("0.80"), MONDAY))
    return TestClient(build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=fx_rates, corporate_actions=actions))


def spy_close(prices: InMemoryPriceData, day: date, price: str) -> None:
    prices.add_close("SPY", Quote(Decimal(price), Currency.USD, datetime(day.year, day.month, day.day, 4, 0, tzinfo=UTC)))


def wallet(client: TestClient, currency: str, deposit_on: date, amount: str) -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": currency, "cash": "0"}).json()["id"]
    timestamp = f"{deposit_on.isoformat()}T09:00:00Z"
    assert client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": amount, "timestamp": timestamp}).status_code == 200
    return wallet_id


def benchmark(client: TestClient, wallet_id: str) -> dict[str, Any]:
    response = client.get(f"/api/wallets/{wallet_id}/benchmark/daily")
    assert response.status_code == 200, response.json()
    result: dict[str, Any] = response.json()
    return result


def test_deposits_buy_spy_on_their_day_and_follow_its_closes(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet(client, "EUR", MONDAY, "1000")
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "208", "timestamp": "2024-06-05T09:00:00Z"})
    spy_close(prices, MONDAY, "500")
    spy_close(prices, TUESDAY, "520")
    spy_close(prices, WEDNESDAY, "520")

    result = benchmark(client, wallet_id)

    assert result["symbol"] == "SPY"
    # Monday: 1000 EUR buys 2.5 SPY at 500 USD x 0.80; Tuesday: 2.5 x 520 x 0.80 = 1040.00 EUR. Wednesday: the 208 EUR
    # withdrawn are 20.8% of the wallet's 1000, so 20.8% of the SPY is sold, leaving 1.98 x 416 = 823.68 EUR. Later days
    # keep Wednesday's close.
    assert [(v["day"], v["value"]) for v in result["values"]][:4] == [
        ("2024-06-03", "1000.00"),
        ("2024-06-04", "1040.00"),
        ("2024-06-05", "823.68"),
        ("2024-06-06", "823.68"),
    ]


def test_a_withdrawal_larger_than_what_spy_would_hold_never_leaves_it_negative(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet(client, "USD", MONDAY, "1000")
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "600", "timestamp": "2024-06-05T09:00:00Z"})
    spy_close(prices, MONDAY, "500")
    spy_close(prices, WEDNESDAY, "250")  # SPY halved: the same 600 would be more than all of it

    values = benchmark(client, wallet_id)["values"]

    # 600 of the wallet's 1000 is 60%: the 2 SPY bought on Monday become 0.8, worth 0.8 x 250 = 200.00.
    assert [(v["day"], v["value"]) for v in values][2] == ("2024-06-05", "200.00")


def test_dividends_are_reinvested_after_the_wallets_withholding_tax(
    client: TestClient, prices: InMemoryPriceData, actions: InMemoryCorporateActions
) -> None:
    wallet_id = wallet(client, "USD", MONDAY, "1000")
    client.patch(f"/api/wallets/{wallet_id}", json={"withholding_rate": "0.2"})
    actions.add_dividend(DividendEvent("SPY", TUESDAY, WEDNESDAY, Decimal("2.50"), Currency.USD, "spy-2024-06"))
    spy_close(prices, MONDAY, "500")
    spy_close(prices, WEDNESDAY, "500")

    values = benchmark(client, wallet_id)["values"]

    # 2 SPY held before the ex-date earn 2 x 2.50 = 5.00 USD, 4.00 after 20% tax, reinvested at Wednesday's close.
    assert [(v["day"], v["value"]) for v in values][1:3] == [("2024-06-04", "1000.00"), ("2024-06-05", "1004.00")]


def test_days_before_spy_has_a_close_are_left_unvalued_and_deposits_wait_for_one(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet(client, "USD", MONDAY, "1000")
    spy_close(prices, TUESDAY, "500")
    spy_close(prices, WEDNESDAY, "510")

    values = benchmark(client, wallet_id)["values"]

    assert [(v["day"], v["value"]) for v in values][:3] == [("2024-06-03", None), ("2024-06-04", "1000.00"), ("2024-06-05", "1020.00")]


def test_an_unknown_wallet_has_no_benchmark(client: TestClient) -> None:
    assert client.get("/api/wallets/00000000-0000-0000-0000-000000000000/benchmark/daily").status_code == 404


def test_another_symbol_can_be_the_benchmark(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet(client, "USD", MONDAY, "1000")
    prices.add_close("QQQ", Quote(Decimal("400"), Currency.USD, datetime(2024, 6, 3, 4, 0, tzinfo=UTC)))
    prices.add_close("QQQ", Quote(Decimal("440"), Currency.USD, datetime(2024, 6, 4, 4, 0, tzinfo=UTC)))

    response = client.get(f"/api/wallets/{wallet_id}/benchmark/daily", params={"symbol": "qqq"})

    result = response.json()
    assert result["symbol"] == "QQQ"
    assert [(v["day"], v["value"]) for v in result["values"]][:2] == [("2024-06-03", "1000.00"), ("2024-06-04", "1100.00")]


def test_a_symbol_without_prices_leaves_every_day_unvalued(client: TestClient) -> None:
    wallet_id = wallet(client, "USD", MONDAY, "1000")

    result = client.get(f"/api/wallets/{wallet_id}/benchmark/daily", params={"symbol": "ZZZZ"}).json()

    assert result["symbol"] == "ZZZZ"
    assert {v["value"] for v in result["values"]} == {None}
