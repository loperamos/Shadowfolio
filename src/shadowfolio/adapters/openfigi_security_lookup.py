"""SecurityLookup from OpenFIGI's mapping API: free and open, run by Bloomberg (https://www.openfigi.com).

Without an API key it takes up to 10 securities per request and about 25 requests a minute, plenty for importing a
statement. A US security (a US ISIN) is asked for on the US composite exchange; any other on the venue it was traded
on, by its MIC: a foreign company also has US over-the-counter tickers that market data does not price.
"""

from collections.abc import Mapping
from itertools import batched
from typing import Any

import httpx2

from shadowfolio.ports.security_lookup import SecurityLookup, SecurityLookupUnavailableError

MAPPING_URL = "https://api.openfigi.com/v3/mapping"
TIMEOUT_SECONDS = 20.0
JOBS_PER_REQUEST = 10  # OpenFIGI's limit without an API key
US_ISIN_PREFIX = "US"
US_COMPOSITE_EXCHANGE = "US"
# OpenFIGI writes share classes with a slash (BRK/B); market data and brokers use a dot (BRK.B).
OPENFIGI_CLASS_SEPARATOR = "/"
CLASS_SEPARATOR = "."
VENUE_SEPARATOR = "."


class OpenFigiSecurityLookup(SecurityLookup):
    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)

    def tickers(self, securities: Mapping[str, str | None]) -> dict[str, str]:
        jobs = [(isin, venue, _job(isin, venue)) for isin, venue in securities.items()]
        askable = [(isin, venue, job) for isin, venue, job in jobs if job is not None]
        tickers: dict[str, str] = {}
        for batch in batched(askable, JOBS_PER_REQUEST, strict=False):
            answers = self._ask([job for _, _, job in batch])
            for (isin, venue, _), answer in zip(batch, answers, strict=True):
                ticker = _ticker(answer, isin, venue)
                if ticker is not None:
                    tickers[isin] = ticker
        return tickers

    def _ask(self, jobs: list[dict[str, str]]) -> list[dict[str, Any]]:
        try:
            response = self._client.post(MAPPING_URL, json=jobs)
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise SecurityLookupUnavailableError(f"OpenFIGI: {error}") from error
        answers: list[dict[str, Any]] = response.json()
        return answers


def _job(isin: str, venue: str | None) -> dict[str, str] | None:
    """What to ask OpenFIGI for: a US security on the US composite exchange, another on its venue (None without one)."""
    if isin.startswith(US_ISIN_PREFIX):
        return {"idType": "ID_ISIN", "idValue": isin, "exchCode": US_COMPOSITE_EXCHANGE}
    if venue:
        return {"idType": "ID_ISIN", "idValue": isin, "micCode": venue}
    return None


def _ticker(answer: dict[str, Any], isin: str, venue: str | None) -> str | None:
    """The ticker in OpenFIGI's answer for one security; None when it found nothing (or the ISIN is not valid)."""
    listings = answer.get("data") or []
    if not listings:
        return None
    ticker: str = listings[0]["ticker"].replace(OPENFIGI_CLASS_SEPARATOR, CLASS_SEPARATOR)
    return ticker if isin.startswith(US_ISIN_PREFIX) else f"{ticker}{VENUE_SEPARATOR}{venue}"
