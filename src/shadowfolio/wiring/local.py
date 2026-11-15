"""Wiring for running on a developer's machine."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from shadowfolio.adapters.alpaca_corporate_actions import AlpacaCorporateActions
from shadowfolio.adapters.alpaca_price_data import FEED, AlpacaConfig, AlpacaPriceData
from shadowfolio.adapters.cached_fx_rates import CachedFxRates
from shadowfolio.adapters.cached_price_data import CachedPriceData
from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.ecb_fx_rates import EcbFxRates
from shadowfolio.adapters.openfigi_security_lookup import OpenFigiSecurityLookup
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallet_changes import WalletChanges
from shadowfolio.usecases.wallets import Wallets

# Past market data is kept in this file, next to the database (and, like it, out of version control). It only holds
# copies of what the providers answered: deleting it loses nothing.
MARKET_CACHE_FILE = "market-cache.db"
# What each provider's data is kept under in that file, so data from one plan or feed never answers for another.
PRICE_SOURCE = f"alpaca/{FEED}"
FX_SOURCE = "ecb"


@dataclass(frozen=True)
class LocalConfig:
    db_path: Path
    alpaca: AlpacaConfig


def build_local_app(config: LocalConfig) -> FastAPI:
    clock = SystemClock()
    wallet_repository = SqliteWalletRepository(config.db_path)
    market_cache = config.db_path.parent / MARKET_CACHE_FILE
    prices = CachedPriceData(AlpacaPriceData(config.alpaca), PRICE_SOURCE, market_cache, clock)
    fx_rates = CachedFxRates(EcbFxRates(clock), FX_SOURCE, market_cache, clock)
    corporate_actions = AlpacaCorporateActions(config.alpaca)
    sync = Sync(wallet_repository, clock, corporate_actions, fx_rates)
    return create_app(
        wallets=Wallets(wallet_repository, clock),
        history=History(wallet_repository, clock, prices, fx_rates, sync),
        valuation=Valuation(wallet_repository, clock, prices, fx_rates),
        comparison=Comparison(wallet_repository, clock, prices, fx_rates, corporate_actions),
        orders=Orders(wallet_repository, clock, prices, WalletChanges(clock, prices, fx_rates, sync)),
        market=Market(prices),
        sync=sync,
        imports=Imports(wallet_repository, WalletChanges(clock, prices, fx_rates, sync), OpenFigiSecurityLookup(), DegiroStatementReader()),
    )
