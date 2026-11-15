"""What is known about a security beyond its price: its fundamentals as the company reported them (yearly revenue, net
income, diluted EPS, shares outstanding), with the P/E and market cap they give at the latest price; and the latest
news about it."""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_company_data import InMemoryCompanyData
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.corporate_actions import DividendEvent
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
        FiscalYear(
            date(2025, 1, 27),
            date(2026, 1, 25),
            Decimal("215938000000"),
            Decimal("120067000000"),
            Decimal("4.90"),
            operating_cash_flow=Decimal("102718000000"),
            capital_spending=Decimal("6042000000"),
            cash=Decimal("10605000000"),
            debt=Decimal("8468000000"),
        ),
    ),
    shares_outstanding=Decimal("24100000000"),
    shares_as_of=date(2026, 8, 21),
    quarters=(
        FiscalYear(date(2024, 1, 29), date(2024, 4, 28), Decimal("26044000000"), Decimal("14881000000"), None),
        FiscalYear(date(2025, 1, 27), date(2025, 4, 27), Decimal("44062000000"), Decimal("18775000000"), None),
    ),
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


def test_each_year_says_how_revenue_grew_and_how_much_of_it_was_kept_as_profit() -> None:
    years = client_with(InMemoryCompanyData({"NVDA": NVDA})).get("/api/securities/NVDA/fundamentals").json()["years"]

    # 2026: 215.938 / 130.497 = +65.47%; 120.067 / 215.938 = 55.60% kept. The first year has no year before it.
    assert [(y["end"], y["revenue_growth"], y["net_margin"]) for y in years] == [
        ("2025-01-26", None, "55.85"),
        ("2026-01-25", "65.47", "55.60"),
    ]


def test_each_year_says_how_much_cash_the_business_made_and_what_it_holds_and_owes() -> None:
    years = client_with(InMemoryCompanyData({"NVDA": NVDA})).get("/api/securities/NVDA/fundamentals").json()["years"]

    # Free cash flow: 102.718 billion from operations less 6.042 billion spent on property and equipment.
    assert [(y["operating_cash_flow"], y["capital_spending"], y["free_cash_flow"], y["cash"], y["debt"]) for y in years] == [
        (None, None, None, None, None),
        ("102718000000", "6042000000", "96676000000", "10605000000", "8468000000"),
    ]


def test_each_quarter_says_how_revenue_grew_on_the_same_quarter_a_year_before() -> None:
    quarters = client_with(InMemoryCompanyData({"NVDA": NVDA})).get("/api/securities/NVDA/fundamentals").json()["quarters"]

    # 44.062 / 26.044 = +69.18%, as quarters are compared with the same season; 18.775 / 44.062 = 42.61% kept.
    assert [(q["end"], q["revenue"], q["revenue_growth"], q["net_margin"]) for q in quarters] == [
        ("2024-04-28", "26044000000", None, "57.14"),
        ("2025-04-27", "44062000000", "69.18", "42.61"),
    ]


def test_the_price_and_pe_ranges_over_a_period_place_the_latest_between_their_lows_and_highs() -> None:
    prices = InMemoryPriceData()
    for day, close in [(date(2026, 1, 20), "147"), (date(2026, 1, 27), "147"), (date(2026, 1, 28), "196")]:
        prices.add_close("NVDA", Quote(Decimal(close), Currency.USD, datetime(day.year, day.month, day.day, 5, 0, tzinfo=UTC)))
    clock = FixedClock(datetime(2026, 1, 29, 12, 0, tzinfo=UTC))
    client = TestClient(build_test_app(clock=clock, prices=prices, company_data=InMemoryCompanyData({"NVDA": NVDA})))

    ranges = client.get("/api/securities/NVDA/ranges", params={"start": "2026-01-19"}).json()

    assert ranges["price"] == {"low": "147", "high": "196", "current": "196", "start": "2026-01-20", "end": "2026-01-28"}
    # Before the fiscal year ending 25 January 2026, the one before's EPS (2.94): 147 / 2.94 = 50. Then 4.90:
    # 147 / 4.90 = 30, and 196 / 4.90 = 40.
    assert ranges["pe"] == {"low": "30.00", "high": "50.00", "current": "40.00", "start": "2026-01-20", "end": "2026-01-28"}


def test_without_fundamentals_there_is_a_price_range_but_no_pe_range() -> None:
    prices = InMemoryPriceData()
    prices.add_close("NNND.XGAT", Quote(Decimal("50"), Currency.EUR, datetime(2026, 1, 20, 5, 0, tzinfo=UTC)))
    clock = FixedClock(datetime(2026, 1, 29, 12, 0, tzinfo=UTC))
    client = TestClient(build_test_app(clock=clock, prices=prices, company_data=InMemoryCompanyData({})))

    ranges = client.get("/api/securities/NNND.XGAT/ranges", params={"start": "2026-01-19"}).json()

    assert (ranges["price"]["current"], ranges["pe"]) == ("50", None)


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


def test_the_calendar_gives_the_next_ex_dividend_date_announced() -> None:
    def dividend(ex: date, paid: date, per_share: str) -> DividendEvent:
        return DividendEvent("MSFT", ex, paid, Decimal(per_share), Currency.USD, f"msft-{ex}")

    corporate_actions = InMemoryCorporateActions(
        dividend(date(2026, 8, 20), date(2026, 9, 11), "0.91"),
        dividend(date(2026, 11, 12), date(2026, 11, 16), "0.91"),  # ex-date past, still to be paid: too late to qualify
        dividend(date(2026, 11, 19), date(2026, 12, 10), "0.98"),
        dividend(date(2027, 2, 18), date(2027, 3, 11), "0.98"),
    )
    clock = FixedClock(datetime(2026, 11, 15, 12, 0, tzinfo=UTC))
    client = TestClient(build_test_app(clock=clock, prices=InMemoryPriceData(), corporate_actions=corporate_actions))

    assert client.get("/api/securities/msft/calendar").json() == {
        "next_ex_dividend": {"ex_date": "2026-11-19", "payable_date": "2026-12-10", "per_share": "0.98", "currency": "USD"}
    }
    assert client.get("/api/securities/NVDA/calendar").json() == {"next_ex_dividend": None}


def test_statistics_describe_the_trend_and_how_much_the_price_swings() -> None:
    """Over the period chosen: volatility (daily moves, a year's worth), the deepest fall from a high, and beta against
    SPY (how much it moves when the market does). The trend is the change over the last 3, 6 and 12 months, whatever
    the period."""
    prices = InMemoryPriceData()

    def close(symbol: str, day: date, price: str) -> None:
        prices.add_close(symbol, Quote(Decimal(price), Currency.USD, datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC)))

    week = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5)]
    # SPY moves +1%, -1%, +1%; the stock exactly twice as much each day: +2%, -2%, +2%.
    for day, spy, stock in zip(week, ["100", "101", "99.99", "100.9899"], ["100", "102", "99.96", "101.9592"], strict=True):
        close("SPY", day, spy)
        close("ACME", day, stock)
    close("ACME", date(2025, 9, 5), "50")  # 6 months before
    close("ACME", date(2025, 12, 5), "80")  # 3 months before
    clock = FixedClock(datetime(2026, 3, 6, 12, 0, tzinfo=UTC))
    client = TestClient(build_test_app(clock=clock, prices=prices))

    result = client.get("/api/securities/acme/statistics", params={"start": "2026-03-02"}).json()

    # Daily moves of +2%, -2%, +2%: a standard deviation of 2.31%, times the square root of 252 trading days.
    assert (result["volatility_percent"], result["max_drawdown_percent"], result["beta"], result["benchmark_symbol"]) == (
        "36.66",
        "-2.00",  # from 102 down to 99.96
        "2.00",
        "SPY",
    )
    # 101.9592 against 80 three months before and 50 six months before; nothing a year before.
    assert (result["three_month_return"], result["six_month_return"], result["one_year_return"]) == ("27.45", "103.92", None)


def test_without_enough_closes_the_statistics_are_unknown() -> None:
    client = TestClient(build_test_app(prices=InMemoryPriceData()))

    result = client.get("/api/securities/ZZZZ/statistics").json()

    assert (result["volatility_percent"], result["max_drawdown_percent"], result["beta"], result["three_month_return"]) == (
        None,
        None,
        None,
        None,
    )
