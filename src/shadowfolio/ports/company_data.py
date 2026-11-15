"""Company information: what a listed company reported about itself."""

from abc import ABC, abstractmethod

from shadowfolio.domain.company import Fundamentals


class CompanyDataUnavailableError(Exception):
    """The provider could not be reached, refused, or is not set up, so nothing is known about the company asked for."""


class CompanyData(ABC):
    @abstractmethod
    def fundamentals(self, symbol: str) -> Fundamentals | None:
        """The company's reported yearly results and shares outstanding, or None if the provider has none for the
        symbol (e.g. a company that does not file with it).

        Raises CompanyDataUnavailableError when the provider cannot answer.
        """
