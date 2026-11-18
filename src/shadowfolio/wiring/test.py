"""Wiring for tests: fakes for every port, nothing persisted."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from shadowfolio.adapters.degiro_statements import DegiroStatementReader
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_access_token_repository import InMemoryAccessTokenRepository
from shadowfolio.adapters.in_memory_company_data import InMemoryCompanyData
from shadowfolio.adapters.in_memory_corporate_actions import InMemoryCorporateActions
from shadowfolio.adapters.in_memory_earnings_calendar import InMemoryEarningsCalendar
from shadowfolio.adapters.in_memory_fx_rates import InMemoryFxRates
from shadowfolio.adapters.in_memory_identity import InMemoryIdentity
from shadowfolio.adapters.in_memory_news import InMemoryNews
from shadowfolio.adapters.in_memory_price_data import InMemoryPriceData
from shadowfolio.adapters.in_memory_provider_key_repository import InMemoryProviderKeyRepository
from shadowfolio.adapters.in_memory_security_lookup import InMemorySecurityLookup
from shadowfolio.adapters.in_memory_user_repository import InMemoryUserRepository
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.adapters.own_key_market_data import OwnKeyMarketData
from shadowfolio.adapters.shared_market_data import SharedMarketData
from shadowfolio.domain.provider_keys import ProviderKey
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.interfaces.web.auth import SignInSettings
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData
from shadowfolio.ports.corporate_actions import CorporateActions
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.fx_rates import FxRates
from shadowfolio.ports.identity import Identity
from shadowfolio.ports.market_data import MarketData, MarketDataSource
from shadowfolio.ports.news import News
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.security_lookup import SecurityLookup
from shadowfolio.usecases.access_tokens import AccessTokens
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.provider_keys import ProviderKeys
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.users import Users
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallet_changes import WalletChanges
from shadowfolio.usecases.wallets import Wallets

DEFAULT_NOW = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)

# Who requests without a sign-in are, unless a test passes its own identity: tests not about sign-in act as one user.
TEST_USER = "test-user"
# The job secret the test app has, unless a test passes its own; and the header calling the jobs with it.
TEST_JOB_TOKEN = "test-job-secret"
JOB = {"Authorization": f"Bearer {TEST_JOB_TOKEN}"}


def build_test_app(
    clock: Clock | None = None,
    prices: PriceData | None = None,
    fx_rates: FxRates | None = None,
    corporate_actions: CorporateActions | None = None,
    earnings_calendar: EarningsCalendar | None = None,
    wallet_repository: InMemoryWalletRepository | None = None,
    security_lookup: SecurityLookup | None = None,
    company_data: CompanyData | None = None,
    news: News | None = None,
    mcp_allowed_hosts: Sequence[str] = (),
    identity: Identity | None = None,
    sign_in: SignInSettings | None = None,
    web_dir: Path | None = None,
    job_token: str | None = TEST_JOB_TOKEN,
    admins: Sequence[str] = (TEST_USER,),
    own_keys: Callable[[str, ProviderKey], MarketData] | None = None,
) -> FastAPI:
    """Pass fakes to control them (or to prepare stored data); otherwise "now" is DEFAULT_NOW, storage is empty and there
    are no prices, rates or corporate actions. TEST_USER is an admin, so tests not about plans meet no plan's limits.

    Every user shares the same market data (`prices`, `corporate_actions`, `news`), unless `own_keys` is given: then
    each user's comes from the key they saved, built by it, and admins without one get the shared market data."""
    clock = clock or FixedClock(DEFAULT_NOW)
    prices = prices or InMemoryPriceData()
    fx_rates = fx_rates or InMemoryFxRates()
    corporate_actions = corporate_actions or InMemoryCorporateActions()
    wallet_repository = wallet_repository or InMemoryWalletRepository()
    users = Users(InMemoryUserRepository(), clock, admins)
    keys = InMemoryProviderKeyRepository()
    shared = MarketData(prices, corporate_actions, news or InMemoryNews())
    market_data: MarketDataSource = (
        SharedMarketData(shared)
        if own_keys is None
        else OwnKeyMarketData(keys, own_keys, shared, lambda user_id: users.user(user_id).uses_server_keys)
    )
    sync = Sync(wallet_repository, clock, market_data, fx_rates)
    market = Market(market_data, clock)
    return create_app(
        wallets=Wallets(wallet_repository, clock, users),
        history=History(wallet_repository, clock, market_data, fx_rates, sync),
        valuation=Valuation(wallet_repository, clock, market_data, fx_rates),
        comparison=Comparison(wallet_repository, clock, market_data, fx_rates),
        orders=Orders(wallet_repository, clock, market_data, fx_rates, WalletChanges(clock, market_data, fx_rates, sync), users),
        securities=Securities(
            company_data or InMemoryCompanyData(), market_data, market, earnings_calendar or InMemoryEarningsCalendar(), clock
        ),
        market=market,
        sync=sync,
        imports=Imports(
            wallet_repository,
            WalletChanges(clock, market_data, fx_rates, sync),
            security_lookup or InMemorySecurityLookup({}),
            DegiroStatementReader(),
        ),
        mcp_allowed_hosts=mcp_allowed_hosts,
        access_tokens=AccessTokens(InMemoryAccessTokenRepository(), wallet_repository, clock, users),
        users=users,
        provider_keys=ProviderKeys(keys, clock, users),
        identity=identity or InMemoryIdentity({}, anonymous=TEST_USER),
        sign_in=sign_in,
        web_dir=web_dir,
        clock=clock,
        job_token=job_token,
    )
