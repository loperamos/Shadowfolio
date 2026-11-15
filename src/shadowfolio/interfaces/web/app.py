"""The HTTP app: one router per area, each calling its use cases and nothing more."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shadowfolio.interfaces.mcp.server import MCP_PATH, mcp_server
from shadowfolio.interfaces.web.comparison import comparison_router
from shadowfolio.interfaces.web.history import history_router
from shadowfolio.interfaces.web.imports import imports_router
from shadowfolio.interfaces.web.market import market_router
from shadowfolio.interfaces.web.orders import orders_router
from shadowfolio.interfaces.web.securities import securities_router
from shadowfolio.interfaces.web.sync import sync_router
from shadowfolio.interfaces.web.valuation import valuation_router
from shadowfolio.interfaces.web.wallets import wallets_router
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.sync import Sync
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
) -> FastAPI:
    # The MCP server for agents, on the same app and use cases; its sessions run while the app does.
    mcp = mcp_server(wallets, valuation, orders, comparison, securities)
    mcp_app = mcp.streamable_http_app(streamable_http_path=MCP_PATH)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    # Operation ids are the route functions' names (e.g. list_wallets), so generated clients get readable names.
    app = FastAPI(title="Shadowfolio", generate_unique_id_function=lambda route: route.name, lifespan=lifespan)
    app.state.mcp = mcp
    app.include_router(wallets_router(wallets), prefix=API_PREFIX)
    app.include_router(history_router(history), prefix=API_PREFIX)
    app.include_router(valuation_router(valuation), prefix=API_PREFIX)
    app.include_router(market_router(market), prefix=API_PREFIX)
    app.include_router(sync_router(sync), prefix=API_PREFIX)
    app.include_router(imports_router(imports), prefix=API_PREFIX)
    app.include_router(comparison_router(comparison), prefix=API_PREFIX)
    app.include_router(orders_router(orders), prefix=API_PREFIX)
    app.include_router(securities_router(securities), prefix=API_PREFIX)
    # Last, so the API's routes are matched first; the MCP app answers at MCP_PATH.
    app.mount("/", mcp_app)
    return app
