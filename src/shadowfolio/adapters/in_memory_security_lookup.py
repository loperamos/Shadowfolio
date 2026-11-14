"""SecurityLookup holding tickers in memory, for tests."""

from collections.abc import Mapping

from shadowfolio.ports.security_lookup import SecurityLookup


class InMemorySecurityLookup(SecurityLookup):
    def __init__(self, tickers: Mapping[str, str]) -> None:
        """`tickers`: the ticker of each ISIN it knows, whatever the venue."""
        self._tickers = dict(tickers)

    def tickers(self, securities: Mapping[str, str | None]) -> dict[str, str]:
        return {isin: self._tickers[isin] for isin in securities if isin in self._tickers}
