"""Access token use cases: creating, listing and revoking the tokens agents use, and telling who a secret belongs to."""

import secrets
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID, uuid4

from shadowfolio.domain.access import HINT_LENGTH, SECRET_PREFIX, AccessToken, Scope, hash_secret
from shadowfolio.domain.errors import InvalidAccessTokenError
from shadowfolio.ports.access_token_repository import AccessTokenRepository
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.wallet_repository import WalletRepository

# Random bytes in a secret (about 256 bits): too many to guess.
SECRET_BYTES = 32
# When a token was last used is recorded at most this often, rather than on every request an agent makes.
USE_RECORDED_EVERY = timedelta(minutes=1)


def new_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(SECRET_BYTES)


class AccessTokens:
    def __init__(
        self, repo: AccessTokenRepository, wallets: WalletRepository, clock: Clock, secret: Callable[[], str] = new_secret
    ) -> None:
        self._repo = repo
        self._wallets = wallets
        self._clock = clock
        self._secret = secret

    def create(self, owner_id: str, name: str, scope: Scope, wallet_ids: list[UUID]) -> tuple[AccessToken, str]:
        """A new token, and its secret: given only now, as only its hash is kept. Each wallet must be the owner's."""
        for wallet_id in wallet_ids:
            wallet = self._wallets.get(wallet_id)
            if wallet is None or wallet.owner_id != owner_id:
                raise InvalidAccessTokenError(f"no wallet {wallet_id}")
        secret = self._secret()
        token = AccessToken(
            uuid4(),
            owner_id,
            name.strip(),
            scope,
            tuple(dict.fromkeys(wallet_ids)),
            hash_secret(secret),
            secret[:HINT_LENGTH],
            self._clock.now(),
        )
        self._repo.add(token)
        return token, secret

    def list(self, owner_id: str) -> list[AccessToken]:
        return self._repo.list_by_owner(owner_id)

    def revoke(self, owner_id: str, token_id: UUID) -> AccessToken | None:
        """Revoke the owner's token: it stops working at once. None if the owner has no such token."""
        token = self._repo.get(token_id)
        if token is None or token.owner_id != owner_id:
            return None
        revoked = token.revoked(self._clock.now())
        self._repo.update(revoked)
        return revoked

    def authenticate(self, secret: str) -> AccessToken | None:
        """The active token with this secret, its use recorded; None for an unknown or revoked one."""
        token = self._repo.find_by_hash(hash_secret(secret))
        if token is None or not token.is_active:
            return None
        now = self._clock.now()
        if token.last_used_at is None or now - token.last_used_at >= USE_RECORDED_EVERY:
            token = token.used_at(now)
            self._repo.update(token)
        return token
