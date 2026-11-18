"""The HTTP app: one router per area, each calling its use cases and nothing more."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from shadowfolio.domain.usage import MCP, Counter
from shadowfolio.interfaces.jobs import Jobs
from shadowfolio.interfaces.mcp.access import RequireToken
from shadowfolio.interfaces.mcp.server import MCP_PATH, mcp_server, transport_security
from shadowfolio.interfaces.web.access import access_router
from shadowfolio.interfaces.web.auth import SignInSettings, auth_router, job_check, sign_in_checks
from shadowfolio.interfaces.web.comparison import comparison_router
from shadowfolio.interfaces.web.history import history_router
from shadowfolio.interfaces.web.imports import imports_router
from shadowfolio.interfaces.web.market import market_router
from shadowfolio.interfaces.web.orders import orders_router
from shadowfolio.interfaces.web.provider_keys import provider_keys_router
from shadowfolio.interfaces.web.securities import securities_router
from shadowfolio.interfaces.web.sync import sync_router
from shadowfolio.interfaces.web.usage import usage_router
from shadowfolio.interfaces.web.users import users_router
from shadowfolio.interfaces.web.valuation import valuation_router
from shadowfolio.interfaces.web.wallets import wallets_router
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.identity import Identity
from shadowfolio.usecases.access_tokens import AccessTokens
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.provider_keys import ProviderKeys
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.usage import Usage
from shadowfolio.usecases.users import Users
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets

# Every API route lives under this prefix, so the rest of the URL space belongs to the web frontend.
API_PREFIX = "/api"


def create_app(
    wallets: Wallets,
    history: History,
    valuation: Valuation,
    market: Market,
    sync: Sync,
    imports: Imports,
    comparison: Comparison,
    orders: Orders,
    securities: Securities,
    access_tokens: AccessTokens,
    users: Users,
    usage: Usage,
    provider_keys: ProviderKeys,
    identity: Identity,
    clock: Clock,
    sign_in: SignInSettings | None = None,  # for the frontend; None when sign-in is not set up
    mcp_allowed_hosts: Sequence[str] = (),  # besides localhost, the addresses agents may reach the MCP server at
    web_dir: Path | None = None,  # the built web app, served at every other path; None when it is served apart (Vite)
    run_jobs: bool = False,  # whether the app runs the system's jobs itself (when deployed; see interfaces.jobs)
    job_token: str | None = None,  # the secret the jobs' endpoints need; None closes them
) -> FastAPI:
    # The MCP server for agents, on the same app and use cases; its sessions run while the app does.
    mcp = mcp_server(wallets, valuation, orders, comparison, securities)
    # Stateless, answering in plain JSON: every request stands alone, as on the REST API, so any instance (or a fresh
    # serverless one) can answer it. The tools need no session: they never stream, push or ask anything back.
    mcp_app = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH, stateless_http=True, json_response=True, transport_security=transport_security(mcp_allowed_hosts)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            running = asyncio.create_task(Jobs(sync, orders, clock).run_forever()) if run_jobs else None
            try:
                yield
            finally:
                if running is not None:
                    running.cancel()
                usage.save()  # the counts recorded since the last save

    # Operation ids are the route functions' names (e.g. list_wallets), so generated clients get readable names.
    app = FastAPI(title="Shadowfolio", generate_unique_id_function=lambda route: route.name, lifespan=lifespan)
    app.state.mcp = mcp
    app.state.access_tokens = access_tokens

    def agent_request(owner_id: str) -> None:
        """An agent's request to the MCP server, for its token's owner: against their plan, and in their usage."""
        users.count_request(owner_id)
        usage.record(owner_id, MCP, Counter.REQUESTS)

    # Every API route signs the user in first, and refuses wallets that are not theirs (see interfaces.web.auth).
    current_user, authorize = sign_in_checks(identity, users, usage, wallets, API_PREFIX)
    api = APIRouter(prefix=API_PREFIX, dependencies=[Depends(authorize)])
    api.include_router(auth_router(sign_in))
    api.include_router(users_router(users, provider_keys, current_user))
    api.include_router(provider_keys_router(provider_keys, current_user))
    api.include_router(usage_router(usage, current_user))
    api.include_router(wallets_router(wallets, current_user))
    api.include_router(history_router(history))
    api.include_router(valuation_router(valuation))
    api.include_router(market_router(market, current_user))
    jobs_only = job_check(job_token)
    api.include_router(sync_router(sync, jobs_only))
    api.include_router(imports_router(imports))
    api.include_router(comparison_router(comparison))
    api.include_router(orders_router(orders, jobs_only))
    api.include_router(securities_router(securities, current_user))
    api.include_router(access_router(access_tokens, current_user))
    app.include_router(api)
    # Last, so the API's routes are matched first: the MCP server at MCP_PATH (every request to it needs an access
    # token), and the web app at every other path, when it is served from here.
    app.mount("/", _Site(RequireToken(mcp_app, access_tokens.authenticate, agent_request), None if web_dir is None else _WebApp(web_dir)))
    return app


__all__ = ["API_PREFIX", "SignInSettings", "create_app"]


# A path whose last part has an extension asks for a file (e.g. /assets/app.js); one without is a route of the web app.
FILE_EXTENSION = "."
INDEX = "index.html"
NOT_FOUND = 404


class _Site:
    """Everything that is not an API route: the MCP server at MCP_PATH, and the web app at every other path; an unknown
    API path stays an API 404 rather than getting the web app's page."""

    def __init__(self, mcp: ASGIApp, web: ASGIApp | None) -> None:
        self._mcp = mcp
        self._web = web

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if path == MCP_PATH or path.startswith(f"{MCP_PATH}/") or self._web is None:
            await self._mcp(scope, receive, send)
        elif path == API_PREFIX or path.startswith(f"{API_PREFIX}/"):
            await JSONResponse({"detail": "Not Found"}, status_code=NOT_FOUND)(scope, receive, send)
        else:
            await self._web(scope, receive, send)


class _WebApp(StaticFiles):
    """The built web app (a single-page app): its files, and its page for its own routes (e.g. /wallets/<id>), which
    the browser then shows. A missing file still answers 404."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != NOT_FOUND or FILE_EXTENSION in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response(INDEX, scope)
