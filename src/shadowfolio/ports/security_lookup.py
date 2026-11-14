"""Identifying securities: from the ISIN a statement gives to the ticker the wallet keeps."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class SecurityLookupUnavailableError(Exception):
    """The lookup could not be reached or answered with an error, so nothing is known about the securities asked for."""


class SecurityLookup(ABC):
    @abstractmethod
    def tickers(self, securities: Mapping[str, str | None]) -> dict[str, str]:
        """For each ISIN, with the MIC of a venue it was traded on when known, its ticker: for a US security (a US
        ISIN), its US ticker; for any other, its ticker on that venue tagged with the venue's MIC (e.g. AIR.XPAR), so it
        cannot be mistaken for a US ticker. ISINs it cannot identify are left out.

        Raises SecurityLookupUnavailableError when the lookup cannot answer.
        """
