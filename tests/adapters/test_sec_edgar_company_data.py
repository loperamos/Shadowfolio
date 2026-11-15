"""How the SEC EDGAR company data talks HTTP, with the network replaced by a fake transport.

The fake answers follow EDGAR's company tickers file and XBRL company facts API, trimmed to the fields the adapter
reads; the live contract test checks the real ones.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx2
import pytest

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.sec_edgar_company_data import FRESH_FOR, SecEdgarCompanyData
from shadowfolio.domain.company import Fundamentals, SharesSource
from shadowfolio.domain.money import Currency
from shadowfolio.ports.company_data import CompanyDataUnavailableError

CONTACT = "Shadowfolio tests@example.com"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
TICKERS = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE"},
}


def entry(start: str, end: str, value: float | int, form: str = "10-K", fp: str = "FY", filed: str = "2026-02-25") -> dict[str, Any]:
    return {"start": start, "end": end, "val": value, "form": form, "fp": fp, "filed": filed}


FACTS: dict[str, Any] = {
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            # Older years under one revenue concept, newer under another, as companies switch.
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [entry("2023-01-30", "2024-01-28", 60922000000, filed="2024-02-21")]}
            },
            "Revenues": {
                "units": {
                    "USD": [
                        entry("2024-01-29", "2025-01-26", 130000000000, filed="2025-02-26"),  # restated a year later:
                        entry("2024-01-29", "2025-01-26", 130497000000),
                        entry("2025-01-27", "2026-01-25", 215938000000),
                        entry("2025-10-27", "2026-01-25", 68127000000, form="10-K", fp="FY"),  # a quarter inside a 10-K
                        entry("2026-01-26", "2026-04-26", 44062000000, form="10-Q", fp="Q1"),
                        # Quarterly reports give the quarter, the year to date, or both (here no third quarter alone).
                        entry("2025-01-27", "2025-04-27", 44062000000, form="10-Q", fp="Q1", filed="2025-05-28"),
                        entry("2025-04-28", "2025-07-27", 46743000000, form="10-Q", fp="Q2", filed="2025-08-27"),
                        entry("2025-01-27", "2025-07-27", 90805000000, form="10-Q", fp="Q2", filed="2025-08-27"),
                        entry("2025-01-27", "2025-10-26", 147811000000, form="10-Q", fp="Q3", filed="2025-11-19"),
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {"USD": [entry("2024-01-29", "2025-01-26", 72880000000), entry("2025-01-27", "2026-01-25", 120067000000)]}
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {
                    "USD": [
                        entry("2024-01-29", "2025-01-26", 64089000000),
                        entry("2025-01-27", "2026-01-25", 102718000000),
                        # Cash flows only for the year to date.
                        entry("2025-01-27", "2025-04-27", 27414000000, form="10-Q", fp="Q1", filed="2025-05-28"),
                        entry("2025-01-27", "2025-07-27", 42563000000, form="10-Q", fp="Q2", filed="2025-08-27"),
                        entry("2025-01-27", "2025-10-26", 66530000000, form="10-Q", fp="Q3", filed="2025-11-19"),
                        # And in the fiscal year under way, not reported as a whole yet.
                        entry("2026-01-26", "2026-04-26", 50340000000, form="10-Q", fp="Q1", filed="2026-05-28"),
                        entry("2026-01-26", "2026-07-26", 90000000000, form="10-Q", fp="Q2", filed="2026-08-26"),
                    ]
                }
            },
            # Capital spending under one concept, then another, as NVIDIA switched.
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [entry("2024-01-29", "2025-01-26", 3236000000)]}},
            "PaymentsToAcquireProductiveAssets": {"units": {"USD": [entry("2025-01-27", "2026-01-25", 6042000000)]}},
            # Balance sheet amounts are at a moment, the fiscal year's end: no start.
            "CashAndCashEquivalentsAtCarryingValue": {
                "units": {
                    "USD": [
                        {"end": "2025-01-26", "val": 8589000000, "form": "10-K", "fp": "FY", "filed": "2026-02-25"},
                        {"end": "2026-01-25", "val": 10605000000, "form": "10-K", "fp": "FY", "filed": "2026-02-25"},
                        {"end": "2026-04-26", "val": 9000000000, "form": "10-Q", "fp": "Q1", "filed": "2026-05-28"},
                        {"end": "2025-10-26", "val": 11486000000, "form": "10-Q", "fp": "Q3", "filed": "2025-11-19"},
                    ]
                }
            },
            "LongTermDebt": {
                "units": {"USD": [{"end": "2026-01-25", "val": 8468000000, "form": "10-K", "fp": "FY", "filed": "2026-02-25"}]}
            },
            "EarningsPerShareDiluted": {
                "units": {
                    "USD/shares": [
                        # Last reported before a later split, so not comparable with the others: left out.
                        entry("2023-01-30", "2024-01-28", 11.93, filed="2024-02-21"),
                        entry("2024-01-29", "2025-01-26", 2.94),
                        entry("2025-01-27", "2026-01-25", 4.9),
                    ]
                }
            },
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        {"end": "2026-05-20", "val": 24300000000, "filed": "2026-05-28"},
                        {"end": "2026-08-21", "val": 24100000000, "filed": "2026-08-26"},
                    ]
                }
            }
        },
    },
}


SUBMISSIONS = {"name": "NVIDIA CORP", "sic": "3674", "sicDescription": "Semiconductors & Related Devices"}


def answer(path: str, facts: dict[str, Any]) -> dict[str, Any]:
    """What EDGAR answers for a request's path: the tickers, a company's profile, or its facts."""
    if path.endswith("company_tickers.json"):
        return TICKERS
    return SUBMISSIONS if "/submissions/" in path else facts


def edgar(
    seen: list[httpx2.Request], status: int = 200, contact: str | None = CONTACT, clock: FixedClock | None = None
) -> SecEdgarCompanyData:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if status != 200:
            return httpx2.Response(status, text="error")
        return httpx2.Response(200, text=json.dumps(answer(request.url.path, FACTS)))

    return SecEdgarCompanyData(contact, clock or FixedClock(NOW), transport=httpx2.MockTransport(handler))


def test_yearly_results_come_from_annual_reports_the_latest_filing_winning() -> None:
    """EPS only for the years in the latest annual report: older figures were not restated for later splits."""
    seen: list[httpx2.Request] = []

    fundamentals = edgar(seen).fundamentals("NVDA")

    assert fundamentals is not None
    assert (fundamentals.company_name, fundamentals.currency) == ("NVIDIA CORP", Currency.USD)
    assert [(y.start, y.end, y.revenue, y.net_income, y.eps_diluted) for y in fundamentals.years] == [
        (date(2023, 1, 30), date(2024, 1, 28), Decimal("60922000000"), None, None),
        (date(2024, 1, 29), date(2025, 1, 26), Decimal("130497000000"), Decimal("72880000000"), Decimal("2.94")),
        (date(2025, 1, 27), date(2026, 1, 25), Decimal("215938000000"), Decimal("120067000000"), Decimal("4.9")),
    ]
    assert (fundamentals.shares_outstanding, fundamentals.shares_as_of) == (Decimal("24100000000"), date(2026, 8, 21))
    assert fundamentals.shares_source is SharesSource.COVER
    # Its industry as the SEC classifies it (SIC), from the company's profile.
    assert fundamentals.industry == "Semiconductors & Related Devices"
    # The company is found by its ticker, and every request says who is asking, as EDGAR requires.
    assert seen[1].url.path == "/api/xbrl/companyfacts/CIK0001045810.json"
    assert seen[2].url.path == "/submissions/CIK0001045810.json"
    assert {request.headers["User-Agent"] for request in seen} == {CONTACT}


def test_cash_flows_and_the_balance_sheet_at_each_year_end_come_from_annual_reports_too() -> None:
    fundamentals = edgar([]).fundamentals("NVDA")

    assert fundamentals is not None
    assert [(y.end, y.operating_cash_flow, y.capital_spending, y.cash, y.debt) for y in fundamentals.years] == [
        (date(2024, 1, 28), None, None, None, None),
        (date(2025, 1, 26), Decimal("64089000000"), Decimal("3236000000"), Decimal("8589000000"), None),
        (date(2026, 1, 25), Decimal("102718000000"), Decimal("6042000000"), Decimal("10605000000"), Decimal("8468000000")),
    ]


def test_quarters_come_from_quarterly_reports_or_the_difference_of_years_to_date() -> None:
    """The third quarter's revenue is nine months less six; each cash flow quarter the year to date less the one
    before, in the year under way too; the fourth quarter the year less nine months. No EPS: earlier quarters' are not
    restated for later splits."""
    fundamentals = edgar([]).fundamentals("NVDA")

    assert fundamentals is not None
    assert [(q.start, q.end, q.revenue, q.operating_cash_flow, q.cash, q.eps_diluted) for q in fundamentals.quarters] == [
        (date(2025, 1, 27), date(2025, 4, 27), Decimal("44062000000"), Decimal("27414000000"), None, None),
        (date(2025, 4, 28), date(2025, 7, 27), Decimal("46743000000"), Decimal("15149000000"), None, None),
        (date(2025, 7, 28), date(2025, 10, 26), Decimal("57006000000"), Decimal("23967000000"), Decimal("11486000000"), None),
        (date(2025, 10, 27), date(2026, 1, 25), Decimal("68127000000"), Decimal("36188000000"), Decimal("10605000000"), None),
        (date(2026, 1, 26), date(2026, 4, 26), Decimal("44062000000"), Decimal("50340000000"), Decimal("9000000000"), None),
        (date(2026, 4, 27), date(2026, 7, 26), None, Decimal("39660000000"), None, None),
    ]


def test_a_share_count_older_than_the_last_fiscal_year_is_not_used() -> None:
    # As for companies with several share classes, whose cover page counts stopped long ago (Berkshire's in 2011).
    stale = {
        **FACTS,
        "facts": {
            **FACTS["facts"],
            "dei": {
                "EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2011-04-29", "val": 941481, "filed": "2011-05-06"}]}}
            },
        },
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=json.dumps(answer(request.url.path, stale)))

    fundamentals = SecEdgarCompanyData(CONTACT, FixedClock(NOW), transport=httpx2.MockTransport(handler)).fundamentals("NVDA")

    assert fundamentals is not None and (fundamentals.shares_outstanding, fundamentals.shares_as_of, fundamentals.shares_source) == (
        None,
        None,
        None,
    )


def with_shares(cover: list[dict[str, Any]], **gaap: Any) -> dict[str, Any]:
    """FACTS with only these cover page counts, and these extra share concepts."""
    return {
        **FACTS,
        "facts": {
            "us-gaap": {**FACTS["facts"]["us-gaap"], **gaap},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": cover}}},
        },
    }


def fundamentals_of(facts: dict[str, Any]) -> Fundamentals:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=json.dumps(answer(request.url.path, facts)))

    found = SecEdgarCompanyData(CONTACT, FixedClock(NOW), transport=httpx2.MockTransport(handler)).fundamentals("NVDA")
    assert found is not None
    return found


def test_without_a_cover_page_count_the_balance_sheets_count_of_every_class_is_used() -> None:
    # Companies with several share classes (Alphabet, Meta) state the cover page count per class, which EDGAR's
    # summary leaves out; the balance sheet counts every class together.
    balance_sheet = {"units": {"shares": [{"end": "2026-04-26", "val": 24250000000, "form": "10-Q", "fp": "Q1", "filed": "2026-05-28"}]}}

    found = fundamentals_of(with_shares([], CommonStockSharesOutstanding=balance_sheet))

    assert (found.shares_outstanding, found.shares_as_of, found.shares_source) == (
        Decimal("24250000000"),
        date(2026, 4, 26),
        SharesSource.BALANCE_SHEET,
    )


def test_without_either_the_quarters_diluted_average_stands_in_approximately() -> None:
    diluted = {
        "units": {
            "shares": [
                entry("2026-01-26", "2026-04-26", 24438000000, form="10-Q", fp="Q1", filed="2026-05-28"),
                entry("2025-01-27", "2026-01-25", 24555000000),  # a whole year: the latest quarter is closer to now
            ]
        }
    }

    found = fundamentals_of(with_shares([], WeightedAverageNumberOfDilutedSharesOutstanding=diluted))

    assert (found.shares_outstanding, found.shares_as_of, found.shares_source) == (
        Decimal("24438000000"),
        date(2026, 4, 26),
        SharesSource.DILUTED_AVERAGE,
    )


def test_a_share_class_is_found_with_edgars_dash() -> None:
    seen: list[httpx2.Request] = []

    edgar(seen).fundamentals("BRK.B")

    assert seen[1].url.path == "/api/xbrl/companyfacts/CIK0001067983.json"


def test_a_symbol_edgar_does_not_list_has_no_fundamentals() -> None:
    assert edgar([]).fundamentals("NNND.XGAT") is None


def test_a_listed_filer_without_financial_facts_has_no_fundamentals() -> None:
    # Funds such as SPY file with the SEC, so EDGAR lists their ticker, but report no company financials: 404.
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx2.Response(200, text=json.dumps({"0": {"cik_str": 884394, "ticker": "SPY", "title": "SPDR S&P 500 ETF TRUST"}}))
        return httpx2.Response(404, text="Not Found")

    assert SecEdgarCompanyData(CONTACT, FixedClock(NOW), transport=httpx2.MockTransport(handler)).fundamentals("SPY") is None


def test_answers_are_kept_for_a_while() -> None:
    seen: list[httpx2.Request] = []
    clock = FixedClock(NOW)
    company_data = edgar(seen, clock=clock)

    company_data.fundamentals("NVDA")
    company_data.fundamentals("NVDA")
    assert len(seen) == 3  # the tickers, the facts and the profile, once
    clock.set(NOW + FRESH_FOR)
    company_data.fundamentals("NVDA")
    assert len(seen) == 6


@pytest.mark.parametrize("status", [403, 503])
def test_an_error_from_edgar_means_unavailable(status: int) -> None:
    with pytest.raises(CompanyDataUnavailableError):
        edgar([], status=status).fundamentals("NVDA")


def test_without_a_contact_nothing_is_asked() -> None:
    seen: list[httpx2.Request] = []

    with pytest.raises(CompanyDataUnavailableError, match="SEC_EDGAR_CONTACT"):
        edgar(seen, contact=None).fundamentals("NVDA")
    assert seen == []
