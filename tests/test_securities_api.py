"""What is known about a security beyond its price: its fundamentals as the company reported them (yearly revenue, net
income, diluted EPS, shares outstanding), with the P/E and market cap they give at the latest price; and the latest
news about it."""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.in_memory_company_data import InMemoryCompanyData
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.money import Currency
from shadowfolio.domain.news import Article
from shadowfolio.domain.valuation import Quote
from shadowfolio.ports.company_data import CompanyDataUnavailableError
from shadowfolio.wiring.test import build_test_app

NVDA = Fundamentals(
    company_name="NVIDIA CORP",
    currency=Currency.USD,
    years=(
        FiscalYear(date(2024, 1, 29), date(2025, 1, 26), Decimal("130497000000"), Decimal("72880000000"), Decimal("2.94")),
        FiscalYear(date(2025, 1, 27), date(2026, 1, 25), Decimal("215938000000"), Decimal("120067000000"), Decimal("4.90")),
    ),
    shares_outstanding=Decimal("24100000000"),
    shares_as_of=date(2026, 8, 21),
)


def client_with(company_data: InMemoryCompanyData) -> TestClient:
    prices = InMemoryPriceData({"NVDA": Quote(Decimal("161.87"), Currency.USD, datetime(2026, 11, 13, 21, 0, tzinfo=UTC))})
    return TestClient(build_test_app(prices=prices, company_data=company_data))


def test_fundamentals_come_with_the_pe_and_market_cap_at_the_latest_price() -> None:
    response = client_with(InMemoryCompanyData({"NVDA": NVDA})).get("/api/securities/nvda/fundamentals")

    assert response.status_code == 200
    result = response.json()
    assert (result["company_name"], result["currency"], result["shares_outstanding"]) == ("NVIDIA CORP", "USD", "24100000000")
    assert [(y["end"], y["revenue"], y["net_income"], y["eps_diluted"]) for y in result["years"]] == [
        ("2025-01-26", "130497000000", "72880000000", "2.94"),
        ("2026-01-25", "215938000000", "120067000000", "4.90"),
    ]
    # At 161.87 USD: 161.87 / 4.90 (the last fiscal year's diluted EPS), and 161.87 x 24.1 billion shares.
    assert (result["price"], result["pe"], result["market_cap"]) == ("161.87", "33.03", "3901067000000.00")


def test_a_symbol_without_fundamentals_returns_404() -> None:
    response = client_with(InMemoryCompanyData({})).get("/api/securities/NNND.XGAT/fundamentals")

    assert (response.status_code, response.json()["detail"]) == (404, "no fundamentals for NNND.XGAT")


def test_fundamentals_are_refused_cleanly_when_they_cannot_be_fetched() -> None:
    company_data = InMemoryCompanyData({"NVDA": NVDA})
    company_data.fail_with(CompanyDataUnavailableError("SEC EDGAR: timed out"))

    response = client_with(company_data).get("/api/securities/NVDA/fundamentals")

    assert (response.status_code, response.json()["detail"]) == (
        422,
        "could not fetch the fundamentals of NVDA right now: SEC EDGAR: timed out",
    )


def test_the_latest_news_about_a_security_newest_first() -> None:
    older = Article(
        "Nvidia partner launches a probe",
        "Megaspeed hired outside lawyers.",
        "benzinga",
        "https://example.com/1",
        datetime(2026, 11, 15, 12, 7, tzinfo=UTC),
    )
    newer = Article(
        "Earnings volatility watch",
        "Options price a 9% move.",
        "benzinga",
        "https://example.com/2",
        datetime(2026, 11, 15, 13, 30, tzinfo=UTC),
    )
    prices = InMemoryPriceData()
    client = TestClient(build_test_app(prices=prices, news=InMemoryNews({"NVDA": [older, newer]})))

    response = client.get("/api/securities/nvda/news")

    assert response.status_code == 200
    assert [(a["headline"], a["source"], a["url"], a["published_at"]) for a in response.json()] == [
        ("Earnings volatility watch", "benzinga", "https://example.com/2", "2026-11-15T13:30:00Z"),
        ("Nvidia partner launches a probe", "benzinga", "https://example.com/1", "2026-11-15T12:07:00Z"),
    ]
    assert client.get("/api/securities/ZZZZ/news").json() == []
