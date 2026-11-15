"""CompanyData from SEC EDGAR: the US regulator's free API of company filings (https://www.sec.gov/edgar).

Its data is public domain. Only companies that file with the SEC are covered (US companies, and some foreign ones);
others have no fundamentals. EDGAR asks every client to say who is asking (an app name and a contact email) in each
request's User-Agent: the contact comes from the configuration and nothing is asked without one.

Yearly results come from annual reports (10-K): when a later report restates a year, the latest filing wins. Answers
are kept in memory for FRESH_FOR: filings change a few times a year.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx2

from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.money import Currency
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TIMEOUT_SECONDS = 30.0
FRESH_FOR = timedelta(days=1)
CONTACT_SETTING = "SEC_EDGAR_CONTACT"
# EDGAR writes share classes with a dash (BRK-B); market data and brokers use a dot (BRK.B).
CLASS_SEPARATOR = "."
EDGAR_CLASS_SEPARATOR = "-"
ANNUAL_FORM = "10-K"
ANNUAL_PERIOD = "FY"
# How long a period must be to be a fiscal year (10-K reports also hold the last quarter's figures).
FISCAL_YEAR_DAYS = range(350, 380)
# The reported concepts read, in US GAAP's taxonomy; revenue under either name, as companies switch.
REVENUE_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
NET_INCOME_CONCEPT = "NetIncomeLoss"
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
        facts = self._get(FACTS_URL.format(cik=cik))
        return _fundamentals(facts)

    def _get(self, url: str) -> Any:
        now = self._clock.now()
        kept = self._kept.get(url)
        if kept is not None and now - kept[0] < FRESH_FOR:
            return kept[1]
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise CompanyDataUnavailableError(f"SEC EDGAR: {error}") from error
        answer = json.loads(response.text, parse_float=Decimal)
        self._kept[url] = (now, answer)
        return answer


def _fundamentals(facts: dict[str, Any]) -> Fundamentals:
    gaap = facts["facts"].get(US_GAAP, {})
    revenue: dict[tuple[date, date], Decimal] = {}
    for concept in REVENUE_CONCEPTS:  # the first concept wins for a year both report
        revenue = _yearly(gaap, concept, USD) | revenue
    net_income = _yearly(gaap, NET_INCOME_CONCEPT, USD)
    eps = _yearly(gaap, EPS_DILUTED_CONCEPT, USD_PER_SHARE, latest_report_only=True)
    periods = sorted(revenue.keys() | net_income.keys() | eps.keys())
    years = tuple(
        FiscalYear(start, end, revenue.get((start, end)), net_income.get((start, end)), eps.get((start, end))) for start, end in periods
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
    )


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
