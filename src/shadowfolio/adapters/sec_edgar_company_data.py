"""CompanyData from SEC EDGAR: the US regulator's free API of company filings (https://www.sec.gov/edgar).

Its data is public domain. Only companies that file with the SEC are covered (US companies, and some foreign ones);
others have no fundamentals. EDGAR asks every client to say who is asking (an app name and a contact email) in each
request's User-Agent: the contact comes from the configuration and nothing is asked without one.

Yearly results come from annual reports (10-K): when a later report restates a year, the latest filing wins. Quarters
come from quarterly reports (10-Q) and annual ones: a quarter reported on its own, or else the difference of two
years to date (cash flows are only reported so), the fourth quarter being the year less nine months. Quarters have no
EPS: a quarter's EPS is only restated for a later stock split if a later report repeats it, so older ones would not be
comparable. Answers are kept in memory for FRESH_FOR: filings change a few times a year.
"""

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import httpx2

from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.money import Currency
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# The company's profile, with its industry as the SEC classifies it (its SIC code's description).
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
INDUSTRY_FIELD = "sicDescription"
TIMEOUT_SECONDS = 30.0
FRESH_FOR = timedelta(days=1)
CONTACT_SETTING = "SEC_EDGAR_CONTACT"
# EDGAR writes share classes with a dash (BRK-B); market data and brokers use a dot (BRK.B).
CLASS_SEPARATOR = "."
EDGAR_CLASS_SEPARATOR = "-"
ANNUAL_FORM = "10-K"
QUARTERLY_FORM = "10-Q"
ANNUAL_PERIOD = "FY"
# How long a period must be to be a fiscal year (10-K reports also hold the last quarter's figures), or a quarter.
FISCAL_YEAR_DAYS = range(350, 380)
QUARTER_DAYS = range(80, 100)
# The reported concepts read, in US GAAP's taxonomy; revenue under either name, as companies switch.
REVENUE_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
NET_INCOME_CONCEPT = "NetIncomeLoss"
OPERATING_CASH_FLOW_CONCEPT = "NetCashProvidedByUsedInOperatingActivities"
# Capital spending, cash and debt also come under more than one name; the first wins for a year both report. Cash
# with restricted cash is the only one some companies (e.g. Berkshire) report; debt is long-term debt, the part due
# within a year included.
CAPITAL_SPENDING_CONCEPTS = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
CASH_CONCEPTS = ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
DEBT_CONCEPTS = ("LongTermDebt",)
EPS_DILUTED_CONCEPT = "EarningsPerShareDiluted"
SHARES_CONCEPT = "EntityCommonStockSharesOutstanding"
US_GAAP = "us-gaap"
DEI = "dei"  # the filing's cover page: who the company is, its shares outstanding
USD = "USD"
USD_PER_SHARE = "USD/shares"
SHARES = "shares"


class SecEdgarCompanyData(CompanyData):
    def __init__(self, contact: str | None, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """`contact` is what each request says about who is asking, e.g. "Shadowfolio you@example.com"; without it,
        nothing is asked. `transport` replaces the network in tests."""
        self._contact = contact
        self._clock = clock
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport, headers={"User-Agent": contact or ""})
        self._kept: dict[str, tuple[datetime, Any]] = {}  # per URL: when it was fetched, and its answer

    def fundamentals(self, symbol: str) -> Fundamentals | None:
        if not self._contact:
            raise CompanyDataUnavailableError(
                f"SEC EDGAR needs a contact: set {CONTACT_SETTING} in .env, e.g. 'Shadowfolio you@example.com'"
            )
        edgar_ticker = symbol.upper().replace(CLASS_SEPARATOR, EDGAR_CLASS_SEPARATOR)
        cik = next((company["cik_str"] for company in self._get(TICKERS_URL).values() if company["ticker"] == edgar_ticker), None)
        if cik is None:
            return None
        # Funds (e.g. SPY) file with the SEC, so their ticker is listed, but have no company financials.
        facts = self._get(FACTS_URL.format(cik=cik), missing_ok=True)
        if facts is None:
            return None
        profile = self._get(SUBMISSIONS_URL.format(cik=cik), missing_ok=True) or {}
        return replace(_fundamentals(facts), industry=profile.get(INDUSTRY_FIELD) or None)

    def _get(self, url: str, missing_ok: bool = False) -> Any:
        """EDGAR's answer for `url`; with `missing_ok`, None when it has nothing there (404)."""
        now = self._clock.now()
        kept = self._kept.get(url)
        if kept is not None and now - kept[0] < FRESH_FOR:
            return kept[1]
        try:
            response = self._client.get(url)
            if missing_ok and response.status_code == HTTPStatus.NOT_FOUND:
                self._kept[url] = (now, None)
                return None
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise CompanyDataUnavailableError(f"SEC EDGAR: {error}") from error
        answer = json.loads(response.text, parse_float=Decimal)
        self._kept[url] = (now, answer)
        return answer


def _fundamentals(facts: dict[str, Any]) -> Fundamentals:
    gaap = facts["facts"].get(US_GAAP, {})
    revenue = _first_reported(gaap, REVENUE_CONCEPTS)
    net_income = _yearly(gaap, NET_INCOME_CONCEPT, USD)
    eps = _yearly(gaap, EPS_DILUTED_CONCEPT, USD_PER_SHARE, latest_report_only=True)
    operating_cash_flow = _yearly(gaap, OPERATING_CASH_FLOW_CONCEPT, USD)
    capital_spending = _first_reported(gaap, CAPITAL_SPENDING_CONCEPTS)
    cash = _first_at_year_end(gaap, CASH_CONCEPTS)
    debt = _first_at_year_end(gaap, DEBT_CONCEPTS)
    periods = sorted(revenue.keys() | net_income.keys() | eps.keys() | operating_cash_flow.keys() | capital_spending.keys())
    # With the fiscal year under way, which starts the day after the last one ended, for its quarters so far.
    under_way = [(periods[-1][1] + timedelta(days=1), periods[-1][1] + timedelta(days=max(FISCAL_YEAR_DAYS)))] if periods else []
    quarters = _quarters(gaap, periods + under_way)
    years = tuple(
        FiscalYear(
            start,
            end,
            revenue.get((start, end)),
            net_income.get((start, end)),
            eps.get((start, end)),
            operating_cash_flow.get((start, end)),
            capital_spending.get((start, end)),
            cash.get(end),
            debt.get(end),
        )
        for start, end in periods
    )
    shares = sorted(
        facts["facts"].get(DEI, {}).get(SHARES_CONCEPT, {}).get("units", {}).get(SHARES, []), key=lambda fact: (fact["end"], fact["filed"])
    )
    latest = shares[-1] if shares else None
    # A count from before the last fiscal year is stale: companies with several share classes stop reporting a single
    # one on the cover page (Berkshire's ends in 2011), and an old count would give a wrong market cap.
    if latest is not None and years and date.fromisoformat(latest["end"]) < years[-1].start:
        latest = None
    return Fundamentals(
        company_name=facts["entityName"],
        currency=Currency.USD,
        years=years,
        shares_outstanding=None if latest is None else Decimal(latest["val"]),
        shares_as_of=None if latest is None else date.fromisoformat(latest["end"]),
        quarters=quarters,
    )


def _quarters(gaap: dict[str, Any], fiscal_years: list[tuple[date, date]]) -> tuple[FiscalYear, ...]:
    """Each fiscal quarter's results, cash flows and balance sheet, oldest first; see the module's description."""
    revenue = _quarterly(gaap, REVENUE_CONCEPTS, fiscal_years)
    net_income = _quarterly(gaap, (NET_INCOME_CONCEPT,), fiscal_years)
    operating_cash_flow = _quarterly(gaap, (OPERATING_CASH_FLOW_CONCEPT,), fiscal_years)
    capital_spending = _quarterly(gaap, CAPITAL_SPENDING_CONCEPTS, fiscal_years)
    cash = _first_at_year_end(gaap, CASH_CONCEPTS, with_quarters=True)
    debt = _first_at_year_end(gaap, DEBT_CONCEPTS, with_quarters=True)
    periods = sorted(revenue.keys() | net_income.keys() | operating_cash_flow.keys() | capital_spending.keys())
    return tuple(
        FiscalYear(
            start,
            end,
            revenue.get((start, end)),
            net_income.get((start, end)),
            None,
            operating_cash_flow.get((start, end)),
            capital_spending.get((start, end)),
            cash.get(end),
            debt.get(end),
        )
        for start, end in periods
    )


def _quarterly(gaap: dict[str, Any], concepts: tuple[str, ...], fiscal_years: list[tuple[date, date]]) -> dict[tuple[date, date], Decimal]:
    """A flow's value for each fiscal quarter, by (start, end): as reported for the quarter, or else the year to date
    less the year to date before it, within each of `fiscal_years`. The first concept wins for a period both report,
    and the latest filing for a period reported again."""
    reported: dict[tuple[date, date], Decimal] = {}
    for concept in concepts:
        by_period: dict[tuple[date, date], Decimal] = {}
        facts = gaap.get(concept, {}).get("units", {}).get(USD, [])
        for fact in sorted(facts, key=lambda fact: fact["filed"]):
            if fact.get("form") in (ANNUAL_FORM, QUARTERLY_FORM) and "start" in fact:
                by_period[(date.fromisoformat(fact["start"]), date.fromisoformat(fact["end"]))] = Decimal(fact["val"])
        reported = by_period | reported
    quarters = {}
    for year_start, year_end in fiscal_years:
        # The year to date at each end reported within the year, oldest first: each less the one before is a quarter.
        to_date = sorted((end, value) for (start, end), value in reported.items() if start == year_start and end <= year_end)
        previous_end, previous_value = None, Decimal(0)
        for end, value in to_date:
            start = year_start if previous_end is None else previous_end + timedelta(days=1)
            if (end - start).days in QUARTER_DAYS:
                quarters[(start, end)] = value - previous_value
            previous_end, previous_value = end, value
    # A quarter reported on its own wins over one worked out.
    return quarters | {period: value for period, value in reported.items() if (period[1] - period[0]).days in QUARTER_DAYS}


def _first_reported(gaap: dict[str, Any], concepts: tuple[str, ...]) -> dict[tuple[date, date], Decimal]:
    """A yearly amount companies report under one of `concepts`: the first wins for a year both report."""
    values: dict[tuple[date, date], Decimal] = {}
    for concept in concepts:
        values = _yearly(gaap, concept, USD) | values
    return values


def _first_at_year_end(gaap: dict[str, Any], concepts: tuple[str, ...], with_quarters: bool = False) -> dict[date, Decimal]:
    """A balance sheet amount at each fiscal year's end from annual reports, or `with_quarters` at each quarter's end
    from quarterly ones too, under one of `concepts`: the first wins for a date both report, and the latest filing for
    a date reported again."""
    forms = (ANNUAL_FORM, QUARTERLY_FORM) if with_quarters else (ANNUAL_FORM,)
    values: dict[date, Decimal] = {}
    for concept in concepts:
        at_end: dict[date, Decimal] = {}
        facts = gaap.get(concept, {}).get("units", {}).get(USD, [])
        for fact in sorted(facts, key=lambda fact: fact["filed"]):
            if fact.get("form") in forms and (with_quarters or fact.get("fp") == ANNUAL_PERIOD) and "start" not in fact:
                at_end[date.fromisoformat(fact["end"])] = Decimal(fact["val"])
        values = at_end | values
    return values


def _yearly(gaap: dict[str, Any], concept: str, unit: str, latest_report_only: bool = False) -> dict[tuple[date, date], Decimal]:
    """A concept's value for each fiscal year in annual reports, by (start, end); the latest filing wins. With
    `latest_report_only`, only the years in the latest annual report (e.g. per-share figures, which earlier reports
    give from before later splits)."""
    values: dict[tuple[date, date], Decimal] = {}
    filed: dict[tuple[date, date], str] = {}
    facts = gaap.get(concept, {}).get("units", {}).get(unit, [])
    for fact in sorted(facts, key=lambda fact: fact["filed"]):
        if fact.get("form") != ANNUAL_FORM or fact.get("fp") != ANNUAL_PERIOD or "start" not in fact:
            continue
        start, end = date.fromisoformat(fact["start"]), date.fromisoformat(fact["end"])
        if (end - start).days in FISCAL_YEAR_DAYS:
            values[(start, end)] = Decimal(fact["val"])
            filed[(start, end)] = fact["filed"]
    if latest_report_only and filed:
        latest = max(filed.values())
        return {period: value for period, value in values.items() if filed[period] == latest}
    return values
