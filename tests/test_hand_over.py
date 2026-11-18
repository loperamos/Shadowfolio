"""The wallets made before sign-in existed, owned by no user ("local"), go to the user the configuration names, with
the agents' tokens for them: once, as nothing is left to hand over afterwards."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.adapters.in_memory_access_token_repository import InMemoryAccessTokenRepository
from shadowfolio.adapters.in_memory_user_repository import InMemoryUserRepository
from shadowfolio.adapters.in_memory_wallet_repository import InMemoryWalletRepository
from shadowfolio.adapters.sqlite_access_token_repository import SqliteAccessTokenRepository
from shadowfolio.adapters.sqlite_wallet_repository import SqliteWalletRepository
from shadowfolio.domain.access import Scope
from shadowfolio.domain.money import Currency
from shadowfolio.ports.access_token_repository import AccessTokenRepository
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.access_tokens import AccessTokens
from shadowfolio.usecases.users import Users
from shadowfolio.usecases.wallets import UNOWNED, Wallets

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
ANA = "auth0|ana"
Repositories = Callable[[], tuple[WalletRepository, AccessTokenRepository]]


@pytest.fixture(params=["in_memory", "sqlite"])
def repositories(request: pytest.FixtureRequest, tmp_path: Path) -> Repositories:
    if request.param == "in_memory":
        both = (InMemoryWalletRepository(), InMemoryAccessTokenRepository())
        return lambda: both
    path = tmp_path / "data" / "test.db"
    return lambda: (SqliteWalletRepository(path), SqliteAccessTokenRepository(path))


def test_the_unowned_wallets_and_their_tokens_go_to_the_user_once(repositories: Repositories) -> None:
    wallet_repo, token_repo = repositories()
    clock = FixedClock(NOW)
    users = Users(InMemoryUserRepository(), clock)
    wallets, tokens = Wallets(wallet_repo, clock, users), AccessTokens(token_repo, wallet_repo, clock, users)
    old = wallets.create(UNOWNED, "DEGIRO", Currency.EUR, Decimal(1000))
    others = wallets.create("auth0|ben", "Ben's", Currency.EUR, Decimal(10))
    token, _ = tokens.create(UNOWNED, "Codex", Scope.READ, [old.id])

    assert (wallets.hand_over(UNOWNED, ANA), tokens.hand_over(UNOWNED, ANA)) == (1, 1)

    wallet_repo, token_repo = repositories()  # as stored
    assert [w.id for w in wallet_repo.list_by_owner(ANA)] == [old.id]
    assert [w.id for w in wallet_repo.list_by_owner("auth0|ben")] == [others.id]
    assert [t.id for t in token_repo.list_by_owner(ANA)] == [token.id]
    assert (wallets.hand_over(UNOWNED, ANA), tokens.hand_over(UNOWNED, ANA)) == (0, 0)  # nothing left
