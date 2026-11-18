"""An HTTP transport that counts each request to a provider, and each that fails (refused with an error status, or
never answered), in front of the real one: given to a provider's adapter, it counts that adapter's calls."""

from http import HTTPStatus

import httpx2

from shadowfolio.domain.usage import Counter, RecordUsage


class CountingTransport(httpx2.BaseTransport):
    def __init__(self, inner: httpx2.BaseTransport, record: RecordUsage) -> None:
        self._inner = inner
        self._record = record

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        self._record(Counter.CALLS, 1)
        try:
            response = self._inner.handle_request(request)
        except httpx2.HTTPError:
            self._record(Counter.ERRORS, 1)
            raise
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            self._record(Counter.ERRORS, 1)
        return response

    def close(self) -> None:
        self._inner.close()
