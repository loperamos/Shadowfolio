"""CompanyData holding fundamentals in memory, for tests."""

from shadowfolio.domain.company import Fundamentals
from shadowfolio.ports.company_data import CompanyData, CompanyDataUnavailableError


class InMemoryCompanyData(CompanyData):
    def __init__(self, fundamentals: dict[str, Fundamentals] | None = None) -> None:
        self._fundamentals = dict(fundamentals or {})
        self._failure: CompanyDataUnavailableError | None = None

    def fail_with(self, error: CompanyDataUnavailableError) -> None:
        """Every request raises `error` from now on, as a provider that cannot be reached."""
        self._failure = error

    def fundamentals(self, symbol: str) -> Fundamentals | None:
        if self._failure is not None:
            raise self._failure
        return self._fundamentals.get(symbol)
