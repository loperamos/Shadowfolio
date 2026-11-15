from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.corporate_actions import SplitEvent
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
        "day_change": "2.46",  # 135.50 - 133.04
        "day_change_percent": "1.85",
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


def test_daily_closes_of_a_symbol_are_its_trading_days_in_the_period() -> None:
    prices = InMemoryPriceData()
    for day, close in [(27, "123.99"), (28, "123.54"), (1, "124.30")]:
        month = 6 if day > 1 else 7
        prices.add_close("NVDA", Quote(Decimal(close), Currency.USD, datetime(2024, month, day, 4, 0, tzinfo=UTC)))
    client = TestClient(build_test_app(clock=FixedClock(datetime(2024, 7, 2, 15, 0, tzinfo=UTC)), prices=prices))

    response = client.get("/api/market/closes/NVDA", params={"start": "2024-06-28"})

    assert response.status_code == 200
    # Friday and Monday: the weekend has no closes of its own, and the period starts on Friday.
    assert [(c["day"], c["close"], c["currency"]) for c in response.json()] == [
        ("2024-06-28", "123.54", "USD"),
        ("2024-07-01", "124.30", "USD"),
    ]


def test_a_symbol_without_prices_has_no_closes() -> None:
    client = TestClient(build_test_app(clock=FixedClock(datetime(2024, 7, 2, 15, 0, tzinfo=UTC))))

    assert client.get("/api/market/closes/ZZZZ", params={"start": "2024-06-28"}).json() == []


def test_a_symbols_closes_are_adjusted_for_its_later_splits() -> None:
    prices = InMemoryPriceData()
    for day, close in [(7, "1208.88"), (10, "121.79")]:
        prices.add_close("NVDA", Quote(Decimal(close), Currency.USD, datetime(2024, 6, day, 4, 0, tzinfo=UTC)))
    actions = InMemoryCorporateActions(SplitEvent("NVDA", date(2024, 6, 10), Decimal(1), Decimal(10), "nvda-2024-split"))
    client = TestClient(
        build_test_app(clock=FixedClock(datetime(2024, 6, 11, 15, 0, tzinfo=UTC)), prices=prices, corporate_actions=actions)
    )

    closes = client.get("/api/market/closes/NVDA", params={"start": "2024-06-07"}).json()

    # Before the 10-for-1 split on 10 June, a share was ten of today's: its close counts as a tenth, so the history
    # reads continuously (as finance sites show it).
    assert [(c["day"], c["close"]) for c in closes] == [("2024-06-07", "120.888"), ("2024-06-10", "121.79")]
