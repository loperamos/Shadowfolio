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
from shadowfolio.domain.company import FiscalYear
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
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {"USD": [entry("2024-01-29", "2025-01-26", 72880000000), entry("2025-01-27", "2026-01-25", 120067000000)]}
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


def edgar(
    seen: list[httpx2.Request], status: int = 200, contact: str | None = CONTACT, clock: FixedClock | None = None
) -> SecEdgarCompanyData:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if status != 200:
            return httpx2.Response(status, text="error")
        body = TICKERS if request.url.path.endswith("company_tickers.json") else FACTS
        return httpx2.Response(200, text=json.dumps(body))

    return SecEdgarCompanyData(contact, clock or FixedClock(NOW), transport=httpx2.MockTransport(handler))


def test_yearly_results_come_from_annual_reports_the_latest_filing_winning() -> None:
    """EPS only for the years in the latest annual report: older figures were not restated for later splits."""
    seen: list[httpx2.Request] = []

    fundamentals = edgar(seen).fundamentals("NVDA")

    assert fundamentals is not None
    assert (fundamentals.company_name, fundamentals.currency) == ("NVIDIA CORP", Currency.USD)
    assert fundamentals.years == (
        FiscalYear(date(2023, 1, 30), date(2024, 1, 28), Decimal("60922000000"), None, None),
        FiscalYear(date(2024, 1, 29), date(2025, 1, 26), Decimal("130497000000"), Decimal("72880000000"), Decimal("2.94")),
        FiscalYear(date(2025, 1, 27), date(2026, 1, 25), Decimal("215938000000"), Decimal("120067000000"), Decimal("4.9")),
    )
    assert (fundamentals.shares_outstanding, fundamentals.shares_as_of) == (Decimal("24100000000"), date(2026, 8, 21))
    # The company is found by its ticker, and every request says who is asking, as EDGAR requires.
    assert seen[1].url.path == "/api/xbrl/companyfacts/CIK0001045810.json"
    assert {request.headers["User-Agent"] for request in seen} == {CONTACT}


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
        return httpx2.Response(200, text=json.dumps(TICKERS if request.url.path.endswith("company_tickers.json") else stale))

    fundamentals = SecEdgarCompanyData(CONTACT, FixedClock(NOW), transport=httpx2.MockTransport(handler)).fundamentals("NVDA")

    assert fundamentals is not None and (fundamentals.shares_outstanding, fundamentals.shares_as_of) == (None, None)


def test_a_share_class_is_found_with_edgars_dash() -> None:
    seen: list[httpx2.Request] = []

    edgar(seen).fundamentals("BRK.B")

    assert seen[1].url.path == "/api/xbrl/companyfacts/CIK0001067983.json"


def test_a_symbol_edgar_does_not_list_has_no_fundamentals() -> None:
    assert edgar([]).fundamentals("NNND.XGAT") is None


def test_answers_are_kept_for_a_while() -> None:
    seen: list[httpx2.Request] = []
    clock = FixedClock(NOW)
    company_data = edgar(seen, clock=clock)

    company_data.fundamentals("NVDA")
    company_data.fundamentals("NVDA")
    assert len(seen) == 2  # the tickers and the facts, once
    clock.set(NOW + FRESH_FOR)
    company_data.fundamentals("NVDA")
    assert len(seen) == 4


@pytest.mark.parametrize("status", [403, 503])
def test_an_error_from_edgar_means_unavailable(status: int) -> None:
    with pytest.raises(CompanyDataUnavailableError):
        edgar([], status=status).fundamentals("NVDA")


def test_without_a_contact_nothing_is_asked() -> None:
    seen: list[httpx2.Request] = []

    with pytest.raises(CompanyDataUnavailableError, match="SEC_EDGAR_CONTACT"):
        edgar(seen, contact=None).fundamentals("NVDA")
    assert seen == []
