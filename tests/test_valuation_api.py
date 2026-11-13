from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceDataUnavailableError
from shadowfolio.wiring.test import build_test_app

NOW = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
QUOTE_TIME = datetime(2026, 3, 2, 14, 59, tzinfo=UTC)


@pytest.fixture
def prices() -> InMemoryPriceData:
    return InMemoryPriceData()


@pytest.fixture
def fx_rates() -> InMemoryFxRates:
    return InMemoryFxRates()


@pytest.fixture
def client(prices: InMemoryPriceData, fx_rates: InMemoryFxRates) -> TestClient:
    return TestClient(build_test_app(clock=FixedClock(NOW), prices=prices, fx_rates=fx_rates))


def wallet_holding(client: TestClient, *trades: dict[str, str]) -> str:
    """An EUR wallet funded with 3000 EUR in 2024, then the given past buys."""
    wallet_id: str = client.post("/api/wallets", json={"name": "W", "currency": "EUR", "cash": "0"}).json()["id"]
    client.post(f"/api/wallets/{wallet_id}/deposits", json={"amount": "3000", "timestamp": "2024-01-02T09:00:00Z"})
    for trade in trades:
        assert client.post(f"/api/wallets/{wallet_id}/buys", json=trade).status_code == 200
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

    response = client.get(f"/api/wallets/{wallet_id}/valuation")
    assert response.status_code == 200
    assert response.json() == {
        "currency": "EUR",
        "cash": "3000",
        "holdings": [],
        "cost": "0.00",
        "gain": "0.00",
        "gain_percent": None,
        "day_change": None,
        "day_change_percent": None,
        "total": "3000",
    }


def test_holdings_are_valued_at_latest_prices_and_converted_into_the_wallet_currency(
    client: TestClient, prices: InMemoryPriceData, fx_rates: InMemoryFxRates
) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY, TSLA_BUY)  # cash left: 3000 - 909.68 - 1479.15 = 611.17 EUR
    prices.set("NVDA", Quote(Decimal("135.50"), Currency.USD, QUOTE_TIME))
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME))
    fx_rates.set(FxRate(Currency.USD, Currency.EUR, Decimal("0.9025"), date(2026, 3, 2)))

    valuation = client.get(f"/api/wallets/{wallet_id}/valuation").json()
    nvda, tsla = valuation["holdings"]
    assert (nvda["symbol"], nvda["value"], nvda["fx_rate"], nvda["value_in_wallet_currency"]) == (
        "NVDA",
        "1084.00",
        {"rate": "0.9025", "as_of": "2026-03-02"},
        "978.31",
    )
    assert (tsla["symbol"], tsla["value"], tsla["fx_rate"], tsla["value_in_wallet_currency"]) == ("TSLA", "1550.00", None, "1550.00")
    assert nvda["as_of"] == "2026-03-02T14:59:00Z"
    assert (valuation["cash"], valuation["total"]) == ("611.17", "3139.48")  # 611.17 + 978.31 + 1550.00
    # Gains against what was paid, fees included: NVDA 978.31 - 909.68, TSLA 1550.00 - 1479.15.
    assert [(h["cost"], h["gain"], h["gain_percent"]) for h in valuation["holdings"]] == [
        ("909.68", "68.63", "7.54"),
        ("1479.15", "70.85", "4.79"),
    ]
    assert (valuation["cost"], valuation["gain"], valuation["gain_percent"]) == ("2388.83", "139.48", "5.84")


def test_day_change_is_the_price_move_since_the_previous_close(
    client: TestClient, prices: InMemoryPriceData, fx_rates: InMemoryFxRates
) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY, TSLA_BUY)
    prices.set("NVDA", Quote(Decimal("135.50"), Currency.USD, QUOTE_TIME, previous_close=Decimal("133.00")))
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME, previous_close=Decimal("315.00")))
    fx_rates.set(FxRate(Currency.USD, Currency.EUR, Decimal("0.9025"), date(2026, 3, 2)))

    valuation = client.get(f"/api/wallets/{wallet_id}/valuation").json()
    # NVDA: 8 x +2.50 USD = +20.00 USD = +18.05 EUR at today's rate (+1.88%); TSLA: 5 x -5.00 EUR = -25.00 EUR (-1.59%).
    assert [(h["previous_close"], h["day_change"], h["day_change_percent"]) for h in valuation["holdings"]] == [
        ("133.00", "18.05", "1.88"),
        ("315.00", "-25.00", "-1.59"),
    ]
    # -6.95 EUR, against what the holdings were worth at the previous close: 978.31 - 18.05 + 1550.00 + 25.00.
    assert (valuation["day_change"], valuation["day_change_percent"]) == ("-6.95", "-0.27")


def test_day_change_is_unknown_when_a_previous_close_is_missing(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet_holding(client, TSLA_BUY)
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME))

    valuation = client.get(f"/api/wallets/{wallet_id}/valuation").json()
    assert (valuation["holdings"][0]["day_change"], valuation["day_change"]) == (None, None)


def test_missing_price_fails_the_valuation(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY, TSLA_BUY)
    prices.set("TSLA", Quote(Decimal("310.00"), Currency.EUR, QUOTE_TIME))

    response = client.get(f"/api/wallets/{wallet_id}/valuation")
    assert response.status_code == 422
    assert response.json()["detail"] == "no price for NVDA"


def test_missing_exchange_rate_fails_the_valuation(client: TestClient, prices: InMemoryPriceData) -> None:
    wallet_id = wallet_holding(client, NVDA_BUY)
    prices.set("NVDA", Quote(Decimal("135.50"), Currency.USD, QUOTE_TIME))

    response = client.get(f"/api/wallets/{wallet_id}/valuation")
    assert response.status_code == 422
    assert response.json()["detail"] == "no USD→EUR rate"


def test_unknown_wallet_valuation_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/wallets/{uuid4()}/valuation").status_code == 404


class UnavailablePriceData(InMemoryPriceData):
    def latest_price(self, symbol: str) -> Quote | None:
        raise PriceDataUnavailableError("down")


def test_a_valuation_is_refused_cleanly_when_prices_cannot_be_fetched() -> None:
    client = TestClient(build_test_app(clock=FixedClock(NOW), prices=UnavailablePriceData()))
    wallet_id = wallet_holding(client, NVDA_BUY)

    response = client.get(f"/api/wallets/{wallet_id}/valuation")
    assert (response.status_code, response.json()["detail"]) == (422, "could not fetch the price of NVDA right now; try again later")
