"""Wiring for tests: fakes for every port, nothing persisted."""

from fastapi import FastAPI

from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.usecases.wallets import Wallets


def build_test_app() -> FastAPI:
    wallets = Wallets(InMemoryWalletRepository())
    return create_app(wallets)
