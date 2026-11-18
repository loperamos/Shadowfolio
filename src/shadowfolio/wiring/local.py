"""Wiring for running on a developer's machine."""

from dataclasses import dataclass, replace
from pathlib import Path

import httpx2
from fastapi import FastAPI

from shadowfolio.adapters.alpaca_corporate_actions import AlpacaCorporateActions
from shadowfolio.adapters.alpaca_news import AlpacaNews
from shadowfolio.adapters.alpaca_price_data import DAILY_FEED, AlpacaConfig, AlpacaPriceData
from shadowfolio.adapters.auth0_identity import Auth0Identity
from shadowfolio.adapters.cached_fx_rates import CachedFxRates
from shadowfolio.adapters.cached_price_data import CachedPriceData
from shadowfolio.adapters.counting_transport import CountingTransport
from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.ecb_fx_rates import EcbFxRates
from shadowfolio.adapters.finnhub_earnings_calendar import FinnhubEarningsCalendar
from shadowfolio.adapters.fixed_identity import FixedIdentity
from shadowfolio.adapters.http_key_checker import HttpKeyChecker
from shadowfolio.adapters.openfigi_security_lookup import OpenFigiSecurityLookup
from shadowfolio.adapters.own_key_market_data import OwnKeyMarketData
from shadowfolio.adapters.sec_edgar_company_data import SecEdgarCompanyData
from shadowfolio.adapters.sqlite_access_token_repository import SqliteAccessTokenRepository
from shadowfolio.adapters.sqlite_provider_key_repository import SqliteProviderKeyRepository
from shadowfolio.adapters.sqlite_usage_repository import SqliteUsageRepository
from shadowfolio.adapters.sqlite_user_repository import SqliteUserRepository
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.adapters.system_clock import SystemClock
from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.domain.usage import SERVER_KEYS, RecordUsage
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.interfaces.web.auth import SignInSettings
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.market_data import MarketData
from shadowfolio.usecases.access_tokens import AccessTokens
from shadowfolio.usecases.accounts import Accounts
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
from shadowfolio.usecases.wallet_changes import WalletChanges
from shadowfolio.usecases.wallets import UNOWNED, Wallets

# Past market data is kept in this file, next to the database (and, like it, out of version control). It only holds
# copies of what the providers answered: deleting it loses nothing.
MARKET_CACHE_FILE = "market-cache.db"
# What each provider's data is kept under in that file, so data from one plan or feed never answers for another.
# Closes are cached under the feed they come from, so ones from another feed are fetched again rather than mixed; and
# those fetched with a user's own key under that user too, so they are only ever shown to them.
PRICE_SOURCE = f"alpaca/{DAILY_FEED}"
OWN_KEY_SOURCE = PRICE_SOURCE + "/user/{user_id}"
FX_SOURCE = "ecb"

# The sign-in provider, as the frontend is told: Auth0, or a fixed user (acting as one, for screenshots).
AUTH0, FIXED = "auth0", "fixed"


@dataclass(frozen=True)
class LocalConfig:
    db_path: Path
    alpaca: AlpacaConfig
    keys_secret: str  # the master key users' market-data keys are encrypted with, kept apart from the database
    edgar_contact: str | None = None  # who SEC EDGAR is told is asking; without it, no fundamentals
    finnhub_key: str | None = None  # for the earnings calendar; without it, no earnings dates
    mcp_allowed_hosts: tuple[str, ...] = ()  # besides localhost, the addresses agents may reach the MCP server at
    # Sign-in through Auth0; without the domain and audience, sign-in is not set up and the API says so.
    auth0_domain: str | None = None
    auth0_client_id: str | None = None
    auth0_audience: str | None = None
    # Who the wallets made before sign-in (owned by no user) go to, with their agents' tokens: the user's id.
    existing_wallets_owner: str | None = None
    admins: tuple[str, ...] = ()  # the user ids that are admins: no limits, and they set other users' tiers
    # The built web app, served by the backend itself (as when deployed); None in development, where Vite serves it.
    web_dir: Path | None = None
    run_jobs: bool = False  # whether the app runs the system's jobs itself, as when deployed (see interfaces.jobs)
    job_token: str | None = None  # the secret the jobs' endpoints need; without it, they are closed


def build_local_app(config: LocalConfig, acting_as: str | None = None) -> FastAPI:
    """The app on this machine. With `acting_as`, every request is that user's without signing in: only for the
    screenshot entry point (see wiring.screenshot), never from the configuration."""
    clock = SystemClock()
    wallet_repository = SqliteWalletRepository(config.db_path)
    market_cache = config.db_path.parent / MARKET_CACHE_FILE
    fx_rates = CachedFxRates(EcbFxRates(clock), FX_SOURCE, market_cache, clock)
    user_repository = SqliteUserRepository(config.db_path)
    users = Users(user_repository, clock, config.admins)
    keys = SqliteProviderKeyRepository(config.db_path, config.keys_secret)
    usage = Usage(SqliteUsageRepository(config.db_path), clock, users)
    # Each user's market data comes from their own Alpaca and Finnhub keys; admins without them use the server's
    # (development plans). Every call to a provider is counted for the key's owner (see usecases.usage).
    finnhub = _finnhub(config.finnhub_key, clock, usage.recorder(SERVER_KEYS, DataProvider.FINNHUB))
    server = replace(_alpaca(config.alpaca, PRICE_SOURCE, market_cache, clock, usage, SERVER_KEYS), earnings_calendar=finnhub)

    def with_own_key(user_id: str, key: ProviderKey) -> MarketData:
        own = AlpacaConfig(key_id=key.key_id or "", secret_key=key.secret)
        return _alpaca(own, OWN_KEY_SOURCE.format(user_id=user_id), market_cache, clock, usage, user_id)

    def with_own_finnhub_key(key: ProviderKey) -> EarningsCalendar:
        return _finnhub(key.secret, clock, usage.recorder(key.owner_id, DataProvider.FINNHUB))

    market_data = OwnKeyMarketData(keys, with_own_key, with_own_finnhub_key, server, lambda user_id: users.user(user_id).uses_server_keys)
    sync = Sync(wallet_repository, clock, market_data, fx_rates)
    market = Market(market_data, clock)
    wallets = Wallets(wallet_repository, clock, users)
    token_repository = SqliteAccessTokenRepository(config.db_path)
    access_tokens = AccessTokens(token_repository, wallet_repository, clock, users)
    if config.existing_wallets_owner:
        # The wallets made before sign-in, and their agents' tokens, go to their user: once, as none are left after.
        wallets.hand_over(UNOWNED, config.existing_wallets_owner)
        access_tokens.hand_over(UNOWNED, config.existing_wallets_owner)
    return create_app(
        wallets=wallets,
        history=History(wallet_repository, clock, market_data, fx_rates, sync),
        valuation=Valuation(wallet_repository, clock, market_data, fx_rates),
        comparison=Comparison(wallet_repository, clock, market_data, fx_rates),
        orders=Orders(wallet_repository, clock, market_data, fx_rates, WalletChanges(clock, market_data, fx_rates, sync), users),
        securities=Securities(SecEdgarCompanyData(config.edgar_contact, clock), market_data, market, clock),
        market=market,
        sync=sync,
        imports=Imports(
            wallet_repository, WalletChanges(clock, market_data, fx_rates, sync), OpenFigiSecurityLookup(), DegiroStatementReader()
        ),
        mcp_allowed_hosts=config.mcp_allowed_hosts,
        access_tokens=access_tokens,
        users=users,
        usage=usage,
        accounts=Accounts(user_repository, wallet_repository, token_repository, keys, usage),
        provider_keys=ProviderKeys(keys, clock, users, HttpKeyChecker(clock)),
        identity=Auth0Identity(config.auth0_domain, config.auth0_audience, clock) if acting_as is None else FixedIdentity(acting_as),
        sign_in=_sign_in(config) if acting_as is None else SignInSettings(provider=FIXED, user_id=acting_as),
        web_dir=config.web_dir,
        clock=clock,
        run_jobs=config.run_jobs,
        job_token=config.job_token,
    )


def _alpaca(config: AlpacaConfig, price_source: str, market_cache: Path, clock: Clock, usage: Usage, user_id: str) -> MarketData:
    """Market data from Alpaca with one key: its daily closes cached under `price_source`, and its calls and cache
    lookups counted for `user_id`, the key's owner."""
    record = usage.recorder(user_id, DataProvider.ALPACA)
    prices = CachedPriceData(AlpacaPriceData(config, clock, _counted(record)), price_source, market_cache, clock, record)
    return MarketData(prices, AlpacaCorporateActions(config, _counted(record)), AlpacaNews(config, _counted(record)))


def _finnhub(key: str | None, clock: Clock, record: RecordUsage) -> EarningsCalendar:
    """Finnhub's earnings calendar with one key, its calls counted for the key's owner."""
    return FinnhubEarningsCalendar(key, clock, _counted(record))


def _counted(record: RecordUsage) -> CountingTransport:
    """The network, each call through it counted (see adapters.counting_transport)."""
    return CountingTransport(httpx2.HTTPTransport(), record)


def _sign_in(config: LocalConfig) -> SignInSettings | None:
    """What the frontend needs to sign users in, when it is all set."""
    if not (config.auth0_domain and config.auth0_client_id and config.auth0_audience):
        return None
    return SignInSettings(provider=AUTH0, domain=config.auth0_domain, client_id=config.auth0_client_id, audience=config.auth0_audience)
