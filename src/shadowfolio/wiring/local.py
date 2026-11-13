"""Wiring for running on a developer's machine."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from shadowfolio.adapters.alpaca_corporate_actions import AlpacaCorporateActions
from shadowfolio.adapters.alpaca_price_data import AlpacaConfig, AlpacaPriceData
from shadowfolio.adapters.ecb_fx_rates import EcbFxRates
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.usecases.history import History
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallets import Wallets


@dataclass(frozen=True)
class LocalConfig:
    db_path: Path
    alpaca: AlpacaConfig


def build_local_app(config: LocalConfig) -> FastAPI:
    clock = SystemClock()
    wallet_repository = SqliteWalletRepository(config.db_path)
    prices = AlpacaPriceData(config.alpaca)
    fx_rates = EcbFxRates(clock)
    sync = Sync(wallet_repository, clock, AlpacaCorporateActions(config.alpaca), fx_rates)
    return create_app(
        wallets=Wallets(wallet_repository, clock),
        history=History(wallet_repository, clock, prices, fx_rates, sync),
        valuation=Valuation(wallet_repository, prices, fx_rates),
        market=Market(prices),
        sync=sync,
    )
