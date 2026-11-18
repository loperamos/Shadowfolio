"""Each request to a provider is counted, and so is each that fails: refused (an error status) or never answered."""

import httpx2
import pytest

from shadowfolio.adapters.counting_transport import CountingTransport
from shadowfolio.domain.usage import Counter


def client(status: int, seen: list[Counter]) -> httpx2.Client:
    transport = CountingTransport(
        httpx2.MockTransport(lambda request: httpx2.Response(status)), lambda counter, n: seen.extend([counter] * n)
    )
    return httpx2.Client(base_url="https://provider.example", transport=transport)


def test_answered_requests_are_counted() -> None:
    seen: list[Counter] = []
    client(200, seen).get("/a")
    client(200, seen).get("/b")

    assert seen == [Counter.CALLS, Counter.CALLS]


def test_refused_requests_count_as_errors() -> None:
    seen: list[Counter] = []
    client(429, seen).get("/a")

    assert seen == [Counter.CALLS, Counter.ERRORS]


def test_requests_never_answered_count_as_errors() -> None:
    seen: list[Counter] = []

    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no network", request=request)

    transport = CountingTransport(httpx2.MockTransport(unreachable), lambda counter, n: seen.extend([counter] * n))
    with pytest.raises(httpx2.ConnectError):
        httpx2.Client(transport=transport).get("https://provider.example/a")
    assert seen == [Counter.CALLS, Counter.ERRORS]
