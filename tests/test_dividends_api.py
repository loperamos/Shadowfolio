"""Cash dividends are credited automatically, on the shares held when their ex-date starts, and follow history changes."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.domain.corporate_actions import DividendEvent
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.ports.fx_rates import FxRatesUnavailableError
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
# Alphabet's real dividend: 0.20 USD a share, ex-date 10 June 2024, paid 17 June 2024.
GOOGL_DIVIDEND = DividendEvent("GOOGL", date(2024, 6, 10), date(2024, 6, 17), Decimal("0.20"), Currency.USD, "googl-2024-06")


class CountingCorporateActions(InMemoryCorporateActions):
    def __init__(self, *events: DividendEvent) -> None:
        super().__init__(*events)
        self.calls = 0

    def dividends(self, symbol: str, start: date, end: date) -> list[DividendEvent]:
        self.calls += 1
        return super().dividends(symbol, start, end)


@pytest.fixture
def actions() -> CountingCorporateActions:
    return CountingCorporateActions(GOOGL_DIVIDEND)


def client_for(actions: InMemoryCorporateActions, clock: FixedClock | None = None) -> TestClient:
    fx = InMemoryFxRates(FxRate(Currency.USD, Currency.EUR, Decimal("0.93"), date(2024, 6, 17)))
    return TestClient(build_test_app(clock=clock or FixedClock(NOW), corporate_actions=actions, fx_rates=fx))


def new_wallet(client: TestClient, currency: str = "USD") -> str:
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": currency, "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "2000", "timestamp": "2024-01-02T09:00:00Z"})
    return wallet_id


def buy_googl(client: TestClient, wallet_id: str, quantity: str, timestamp: str) -> dict[str, Any]:
    body = {"symbol": "GOOGL", "quantity": quantity, "price": "170", "price_currency": "USD", "timestamp": timestamp}
    if client.get(f"/api/wallets/{wallet_id}").json()["currency"] != "USD":
        body["settled_amount"] = str(Decimal(quantity) * 158)
    response = client.post(f"/api/wallets/{wallet_id}/buys", json=body)
    assert response.status_code == 200, response.json()
    result: dict[str, Any] = response.json()
    return result


def dividends(client: TestClient, wallet_id: str) -> list[dict[str, Any]]:
    return [op for op in client.get(f"/api/wallets/{wallet_id}/operations").json() if op["type"] == "dividend"]


def test_shares_held_before_the_ex_date_earn_the_dividend_on_its_payment_date(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")

    [dividend] = dividends(client, wallet_id)
    assert (dividend["timestamp"], dividend["quantity"], dividend["price"], dividend["amount"], dividend["automatic"]) == (
        "2024-06-17T00:00:00Z",
        "3",
        "0.20",
        "0.60",
        True,
    )
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "1490.60"  # 2000 - 510 + 0.60


def test_a_buy_on_the_ex_date_does_not_qualify(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-06-10T15:00:00Z")

    assert dividends(client, wallet_id) == []


def test_a_dividend_in_another_currency_is_converted_at_the_payment_days_rate(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client, "EUR")
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")

    [dividend] = dividends(client, wallet_id)
    assert (dividend["price"], dividend["price_currency"], dividend["fx_rate"], dividend["amount"]) == ("0.20", "USD", "0.93", "0.56")


def test_changing_the_past_recomputes_the_dividend_without_asking_the_provider(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")
    calls = actions.calls

    buy_googl(client, wallet_id, "2", "2024-05-15T15:00:00Z")  # inside the checked period, before the ex-date

    assert dividends(client, wallet_id)[0]["amount"] == "1.00"  # 5 x 0.20
    assert actions.calls == calls


def test_a_change_that_takes_away_a_dividend_already_spent_is_refused(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")  # cash 1490.00, then 1490.60 with the dividend
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "1490.60", "timestamp": "2024-06-20T09:00:00Z"})
    buy_id = next(op["id"] for op in client.get(f"/api/wallets/{wallet_id}/operations").json() if op["type"] == "buy")

    # Moved after the ex-date, the buy no longer earns the dividend, so the withdrawal would overdraw the wallet.
    moved = {
        "type": "buy",
        "symbol": "GOOGL",
        "quantity": "3",
        "price": "170",
        "price_currency": "USD",
        "timestamp": "2024-06-11T15:00:00Z",
    }
    response = client.put(f"/api/wallets/{wallet_id}/operations/{buy_id}", json=moved)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("cash would be -0.60")
    assert dividends(client, wallet_id)[0]["amount"] == "0.60"


def test_the_daily_sync_credits_a_dividend_paid_since_once(actions: CountingCorporateActions) -> None:
    clock = FixedClock(datetime(2024, 6, 12, 12, 0, tzinfo=UTC))  # after the ex-date, before the payment
    client = client_for(actions, clock)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")
    assert dividends(client, wallet_id) == []

    clock.set(datetime(2024, 6, 18, 12, 0, tzinfo=UTC))
    client.post("/api/sync")
    client.post("/api/sync")
    assert [d["amount"] for d in dividends(client, wallet_id)] == ["0.60"]


def test_dividends_are_read_only_and_go_with_the_last_trade_of_their_symbol(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")
    [dividend] = dividends(client, wallet_id)
    assert client.delete(f"/api/wallets/{wallet_id}/operations/{dividend['id']}").status_code == 422

    buy_id = next(op["id"] for op in client.get(f"/api/wallets/{wallet_id}/operations").json() if op["type"] == "buy")
    client.delete(f"/api/wallets/{wallet_id}/operations/{buy_id}")
    assert dividends(client, wallet_id) == []
    assert client.get(f"/api/wallets/{wallet_id}").json()["cash"] == "2000"


class UnavailableFxRates(InMemoryFxRates):
    def rate_on(self, base: Currency, quote: Currency, day: date) -> FxRate | None:
        raise FxRatesUnavailableError("down")


def test_without_exchange_rates_a_dividend_in_another_currency_is_not_guessed(actions: CountingCorporateActions) -> None:
    client = TestClient(build_test_app(clock=FixedClock(NOW), corporate_actions=actions, fx_rates=UnavailableFxRates()))
    wallet_id = new_wallet(client, "EUR")
    body = {
        "symbol": "GOOGL",
        "quantity": "3",
        "price": "170",
        "price_currency": "USD",
        "timestamp": "2024-05-01T15:00:00Z",
        "settled_amount": "474",
    }

    response = client.post(f"/api/wallets/{wallet_id}/buys", json=body)
    assert (response.status_code, response.json()["detail"]) == (
        422,
        "could not fetch exchange rates for dividends right now; try again later",
    )
    assert client.get(f"/api/wallets/{wallet_id}").json()["holdings"] == {}


def test_the_wallets_withholding_tax_is_taken_from_every_dividend(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")

    response = client.patch(f"/api/wallets/{wallet_id}", json={"withholding_rate": "0.15"})

    assert response.status_code == 200
    assert (response.json()["withholding_rate"], response.json()["cash"]) == ("0.15", "1490.51")  # 2000 - 510 + 0.51
    [dividend] = dividends(client, wallet_id)
    assert (dividend["gross"], dividend["withholding"], dividend["amount"]) == ("0.60", "0.09", "0.51")


def test_a_higher_withholding_tax_that_takes_away_dividend_cash_already_spent_is_refused(actions: CountingCorporateActions) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)
    buy_googl(client, wallet_id, "3", "2024-05-01T15:00:00Z")
    client.post(f"/api/wallets/{wallet_id}/withdrawals", json={"amount": "1490.60", "timestamp": "2024-06-20T09:00:00Z"})

    response = client.patch(f"/api/wallets/{wallet_id}", json={"withholding_rate": "0.15"})

    assert response.status_code == 422
    assert response.json()["detail"].startswith("cash would be -0.09")
    assert client.get(f"/api/wallets/{wallet_id}").json()["withholding_rate"] == "0"


@pytest.mark.parametrize("rate", ["-0.01", "1"])
def test_a_withholding_tax_outside_0_to_100_percent_is_rejected(actions: CountingCorporateActions, rate: str) -> None:
    client = client_for(actions)
    wallet_id = new_wallet(client)

    response = client.patch(f"/api/wallets/{wallet_id}", json={"withholding_rate": rate})

    assert response.status_code == 422
    assert response.json()["detail"] == "withholding tax must be at least 0% and below 100%"
