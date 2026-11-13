from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.money import Currency
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.price_data import PriceDataUnavailableError
from shadowfolio.wiring.test import build_test_app


def test_latest_quote_for_a_symbol() -> None:
    prices = InMemoryPriceData(
        {"NVDA": Quote(Decimal("135.50"), Currency.USD, datetime(2026, 3, 2, 20, 59, tzinfo=UTC), Decimal("133.04"))}
    )
    client = TestClient(build_test_app(prices=prices))

    response = client.get("/api/market/quotes/NVDA")
    assert response.status_code == 200
    assert response.json() == {
        "symbol": "NVDA",
        "price": "135.50",
        "currency": "USD",
        "as_of": "2026-03-02T20:59:00Z",
        "previous_close": "133.04",
    }


def test_symbol_without_price_returns_404() -> None:
    client = TestClient(build_test_app())

    response = client.get("/api/market/quotes/ZZZZ")
    assert response.status_code == 404
    assert response.json()["detail"] == "no price for ZZZZ"


class UnavailablePriceData(InMemoryPriceData):
    def latest_price(self, symbol: str) -> Quote | None:
        raise PriceDataUnavailableError("down")


def test_a_quote_is_refused_cleanly_when_prices_cannot_be_fetched() -> None:
    client = TestClient(build_test_app(prices=UnavailablePriceData()))

    response = client.get("/api/market/quotes/NVDA")
    assert (response.status_code, response.json()["detail"]) == (422, "could not fetch the price of NVDA right now; try again later")
