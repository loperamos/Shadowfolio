"""Wiring for running on a developer's machine."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.usecases.history import History
from shadowfolio.usecases.wallets import Wallets


@dataclass(frozen=True)
class LocalConfig:
    db_path: Path


def build_local_app(config: LocalConfig) -> FastAPI:
    clock = SystemClock()
    wallet_repository = SqliteWalletRepository(config.db_path)
    return create_app(wallets=Wallets(wallet_repository, clock), history=History(wallet_repository, clock))
