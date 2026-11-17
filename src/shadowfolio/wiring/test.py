"""Wiring for tests: fakes for every port, nothing persisted."""

from collections.abc import Sequence
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
from shadowfolio.adapters.in_memory_security_lookup import InMemorySecurityLookup
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.interfaces.web.app import create_app
from shadowfolio.interfaces.web.auth import SignInSettings
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.company_data import CompanyData
from shadowfolio.ports.corporate_actions import CorporateActions
from shadowfolio.ports.earnings_calendar import EarningsCalendar
from shadowfolio.ports.fx_rates import FxRates
from shadowfolio.ports.identity import Identity
from shadowfolio.ports.news import News
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.security_lookup import SecurityLookup
from shadowfolio.usecases.access_tokens import AccessTokens
from shadowfolio.usecases.comparison import Comparison
from shadowfolio.usecases.history import History
from shadowfolio.usecases.imports import Imports
from shadowfolio.usecases.market import Market
from shadowfolio.usecases.orders import Orders
from shadowfolio.usecases.securities import Securities
from shadowfolio.usecases.sync import Sync
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
) -> FastAPI:
    """Pass fakes to control them (or to prepare stored data); otherwise "now" is DEFAULT_NOW, storage is empty and there
    are no prices, rates or corporate actions."""
    clock = clock or FixedClock(DEFAULT_NOW)
    prices = prices or InMemoryPriceData()
    fx_rates = fx_rates or InMemoryFxRates()
    corporate_actions = corporate_actions or InMemoryCorporateActions()
    wallet_repository = wallet_repository or InMemoryWalletRepository()
    sync = Sync(wallet_repository, clock, corporate_actions, fx_rates)
    market = Market(prices, clock, corporate_actions)
    return create_app(
        wallets=Wallets(wallet_repository, clock),
        history=History(wallet_repository, clock, prices, fx_rates, sync),
        valuation=Valuation(wallet_repository, clock, prices, fx_rates),
        comparison=Comparison(wallet_repository, clock, prices, fx_rates, corporate_actions),
        orders=Orders(wallet_repository, clock, prices, fx_rates, WalletChanges(clock, prices, fx_rates, sync)),
        securities=Securities(
            company_data or InMemoryCompanyData(),
            prices,
            news or InMemoryNews(),
            market,
            corporate_actions,
            earnings_calendar or InMemoryEarningsCalendar(),
            clock,
        ),
        market=market,
        sync=sync,
        imports=Imports(
            wallet_repository,
            WalletChanges(clock, prices, fx_rates, sync),
            security_lookup or InMemorySecurityLookup({}),
            DegiroStatementReader(),
        ),
        mcp_allowed_hosts=mcp_allowed_hosts,
        access_tokens=AccessTokens(InMemoryAccessTokenRepository(), wallet_repository, clock),
        identity=identity or InMemoryIdentity({}, anonymous=TEST_USER),
        sign_in=sign_in,
        web_dir=web_dir,
        clock=clock,
        job_token=job_token,
    )
