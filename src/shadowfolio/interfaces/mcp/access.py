"""Who is calling the MCP server: every request needs an access token, as `Authorization: Bearer <secret>`. Requests
without a valid one are refused (401) before reaching the tools; the token of the others is what the tools check
(see `current_token`)."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

from shadowfolio.domain.access import AccessToken

BEARER = "bearer"
AUTHORIZATION = b"authorization"
UNAUTHORIZED = 401
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

    def __init__(self, app: ASGIApp, authenticate: Callable[[str], AccessToken | None]) -> None:
        self._app = app
        self._authenticate = authenticate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        secret = _bearer(dict(scope["headers"]).get(AUTHORIZATION, b"").decode())
        token = None if secret is None else self._authenticate(secret)
        if token is None:
            await _refuse(send, MISSING if secret is None else INVALID)
            return
        with acting_with(token):
            await self._app(scope, receive, send)


def _bearer(header: str) -> str | None:
    kind, _, secret = header.partition(" ")
    return secret.strip() or None if kind.lower() == BEARER else None


async def _refuse(send: Send, message: str) -> None:
    body = json.dumps({"error": message}).encode()
    headers = [(b"content-type", b"application/json"), (b"www-authenticate", b'Bearer realm="shadowfolio"')]
    await send({"type": "http.response.start", "status": UNAUTHORIZED, "headers": headers})
    await send({"type": "http.response.body", "body": body})
