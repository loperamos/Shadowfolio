"""The HTTP app: one router per area, each calling its use cases and nothing more."""

from fastapi import FastAPI

from shadowfolio.interfaces.web.history import history_router
from shadowfolio.interfaces.web.market import market_router
from shadowfolio.interfaces.web.valuation import valuation_router
from shadowfolio.interfaces.web.wallets import wallets_router
from shadowfolio.usecases.history import History
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets

# Every API route lives under this prefix, so the rest of the URL space belongs to the web frontend.
API_PREFIX = "/api"


def create_app(wallets: Wallets, history: History, valuation: Valuation, market: Market) -> FastAPI:
    # Operation ids are the route functions' names (e.g. list_wallets), so generated clients get readable names.
    app = FastAPI(title="Shadowfolio", generate_unique_id_function=lambda route: route.name)
    app.include_router(wallets_router(wallets), prefix=API_PREFIX)
    app.include_router(history_router(history), prefix=API_PREFIX)
    app.include_router(valuation_router(valuation), prefix=API_PREFIX)
    app.include_router(market_router(market), prefix=API_PREFIX)
    return app
