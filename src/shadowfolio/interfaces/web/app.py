"""The HTTP app: one router per area, each calling its use cases and nothing more."""

from fastapi import FastAPI

from shadowfolio.interfaces.web.history import history_router
from shadowfolio.interfaces.web.wallets import wallets_router
from shadowfolio.usecases.history import History
from shadowfolio.usecases.wallets import Wallets


def create_app(wallets: Wallets, history: History) -> FastAPI:
    app = FastAPI(title="Shadowfolio")
    app.include_router(wallets_router(wallets))
    app.include_router(history_router(history))
    return app
