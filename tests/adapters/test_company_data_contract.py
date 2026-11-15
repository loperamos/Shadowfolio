"""Contract every CompanyData adapter must meet.

Runs against the in-memory fake by default; SEC EDGAR runs only with `pytest -m live`, with the contact in .env.
"""

import os
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from shadowfolio.adapters.in_memory_company_data import InMemoryCompanyData
from shadowfolio.adapters.sec_edgar_company_data import CONTACT_SETTING, SecEdgarCompanyData
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.domain.company import FiscalYear, Fundamentals
from shadowfolio.domain.money import Currency
from shadowfolio.ports.company_data import CompanyData

KNOWN_SYMBOL = "NVDA"
UNKNOWN_SYMBOL = "ZZZZZZZZ"


def _in_memory() -> CompanyData:
    year = FiscalYear(date(2025, 1, 27), date(2026, 1, 25), Decimal("215938000000"), Decimal("120067000000"), Decimal("4.9"))
    return InMemoryCompanyData(
        {KNOWN_SYMBOL: Fundamentals("NVIDIA CORP", Currency.USD, (year,), Decimal("24100000000"), date(2026, 8, 21))}
    )


def _sec_edgar() -> CompanyData:
    load_dotenv()
    contact = os.environ.get(CONTACT_SETTING)
    if not contact:
        pytest.skip(f"{CONTACT_SETTING} is not set")
    return SecEdgarCompanyData(contact, SystemClock())


ADAPTERS: dict[str, Callable[[], CompanyData]] = {"in_memory": _in_memory, "sec_edgar": _sec_edgar}


@pytest.fixture(params=["in_memory", pytest.param("sec_edgar", marks=pytest.mark.live)])
def company_data(request: pytest.FixtureRequest) -> CompanyData:
    return ADAPTERS[request.param]()


def test_a_known_company_has_yearly_results_and_shares(company_data: CompanyData) -> None:
    fundamentals = company_data.fundamentals(KNOWN_SYMBOL)

    assert fundamentals is not None
    assert fundamentals.company_name and fundamentals.currency is Currency.USD
    latest = fundamentals.years[-1]
    assert latest.end > latest.start
    assert latest.revenue is not None and latest.revenue > 0
    assert isinstance(latest.eps_diluted, Decimal)
    assert fundamentals.shares_outstanding is not None and fundamentals.shares_outstanding > 0


def test_an_unknown_symbol_has_no_fundamentals(company_data: CompanyData) -> None:
    assert company_data.fundamentals(UNKNOWN_SYMBOL) is None
