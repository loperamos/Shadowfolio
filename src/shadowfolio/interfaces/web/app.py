"""The HTTP app: one router per area, each calling its use cases and nothing more."""

from fastapi import FastAPI

from shadowfolio.interfaces.web.comparison import comparison_router
from shadowfolio.interfaces.web.history import history_router
from shadowfolio.interfaces.web.imports import imports_router
from shadowfolio.interfaces.web.market import market_router
from shadowfolio.interfaces.web.orders import orders_router
from shadowfolio.interfaces.web.sync import sync_router
from shadowfolio.interfaces.web.valuation import valuation_router
from shadowfolio.interfaces.web.wallets import wallets_router
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
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
) -> FastAPI:
    # Operation ids are the route functions' names (e.g. list_wallets), so generated clients get readable names.
    app = FastAPI(title="Shadowfolio", generate_unique_id_function=lambda route: route.name)
    app.include_router(wallets_router(wallets), prefix=API_PREFIX)
    app.include_router(history_router(history), prefix=API_PREFIX)
    app.include_router(valuation_router(valuation), prefix=API_PREFIX)
    app.include_router(market_router(market), prefix=API_PREFIX)
    app.include_router(sync_router(sync), prefix=API_PREFIX)
    app.include_router(imports_router(imports), prefix=API_PREFIX)
    app.include_router(comparison_router(comparison), prefix=API_PREFIX)
    app.include_router(orders_router(orders), prefix=API_PREFIX)
    return app
