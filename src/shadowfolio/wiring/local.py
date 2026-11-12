"""Wiring for running on a developer's machine."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.usecases.wallets import Wallets


@dataclass(frozen=True)
class LocalConfig:
    db_path: Path


def build_local_app(config: LocalConfig) -> FastAPI:
    wallets = Wallets(SqliteWalletRepository(config.db_path))
    return create_app(wallets)
