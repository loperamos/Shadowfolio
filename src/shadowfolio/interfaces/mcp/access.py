"""Who is calling the MCP server: every request needs an access token, as `Authorization: Bearer <secret>`. Requests
without a valid one are refused (401) before reaching the tools; the token of the others is what the tools check
(see `current_token`). Each request counts against the owner's plan, as on the web API: over it, 429."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

from shadowfolio.domain.access import AccessToken
from shadowfolio.domain.errors import RateLimitError

BEARER = "bearer"
AUTHORIZATION = b"authorization"
UNAUTHORIZED, TOO_MANY_REQUESTS = 401, 429
MISSING = "an access token is needed: send it as 'Authorization: Bearer <token>' (create one in Shadowfolio)"
INVALID = "the access token is not valid, or was revoked"

_current: ContextVar[AccessToken | None] = ContextVar("access_token", default=None)


def current_token() -> AccessToken | None:
    """The token the current request came with; None outside a request that passed the check."""
    return _current.get()


@contextmanager
def acting_with(token: AccessToken | None) -> Iterator[None]:
    """Run as `token`, as a request carrying it does."""
    reset = _current.set(token)
    try:
        yield
    finally:
        _current.reset(reset)


class RequireToken:
    """ASGI middleware in front of the MCP app: lets through only requests with a valid token, and runs them as it."""

    def __init__(self, app: ASGIApp, authenticate: Callable[[str], AccessToken | None], count_request: Callable[[str], None]) -> None:
        """`count_request` counts a request by a user (the token's owner), raising RateLimitError over their plan."""
        self._app = app
        self._authenticate = authenticate
        self._count_request = count_request

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        secret = _bearer(dict(scope["headers"]).get(AUTHORIZATION, b"").decode())
        token = None if secret is None else self._authenticate(secret)
        if token is None:
            await _refuse(send, MISSING if secret is None else INVALID)
            return
        try:
            self._count_request(token.owner_id)
        except RateLimitError as error:
            await _refuse(send, str(error), TOO_MANY_REQUESTS, [(b"retry-after", str(error.retry_after_seconds).encode())])
            return
        with acting_with(token):
            await self._app(scope, receive, send)


def _bearer(header: str) -> str | None:
    kind, _, secret = header.partition(" ")
    return secret.strip() or None if kind.lower() == BEARER else None


async def _refuse(send: Send, message: str, status: int = UNAUTHORIZED, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"error": message}).encode()
    if headers is None:
        headers = [(b"www-authenticate", b'Bearer realm="shadowfolio"')]
    headers = [(b"content-type", b"application/json"), *headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
