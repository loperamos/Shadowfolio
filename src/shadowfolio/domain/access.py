"""Access tokens: what lets an agent use the user's wallets, and how far.

A token has a scope (read; or trading: read, and place or cancel orders now) and the wallets it may use. Its secret is
given once, when created; only a hash of it is kept, so a stolen database gives no usable token.
"""

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from shadowfolio.domain.errors import InvalidAccessTokenError

# Starts every secret, so secret scanners (e.g. GitHub's) can recognise a leaked one.
SECRET_PREFIX = "sfo_"
# How much of the secret is kept in clear, to tell tokens apart: the prefix and a few characters.
HINT_LENGTH = 8


class Scope(StrEnum):
    READ = "read"  # wallets and securities, and order previews
    TRADING = "trading"  # read, and place or cancel orders now


@dataclass(frozen=True)
class AccessToken:
    id: UUID
    owner_id: str
    name: str  # what it is for, e.g. "Codex on my laptop"
    scope: Scope
    wallet_ids: tuple[UUID, ...]  # the wallets it may use
    secret_hash: str  # of the secret, never the secret itself (see hash_secret)
    hint: str  # the secret's first characters, to recognise it
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidAccessTokenError("a token needs a name, to tell what it is for")
        if not self.wallet_ids:
            raise InvalidAccessTokenError("a token needs at least one wallet it may use")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def may_trade(self) -> bool:
        return self.scope is Scope.TRADING

    def reaches(self, wallet_id: UUID) -> bool:
        return wallet_id in self.wallet_ids

    def used_at(self, at: datetime) -> Self:
        return replace(self, last_used_at=at)

    def revoked(self, at: datetime) -> Self:
        return self if self.revoked_at is not None else replace(self, revoked_at=at)


def hash_secret(secret: str) -> str:
    """The hash kept for a secret. Secrets are long and random, so a plain SHA-256 is enough (no salt or slow hash)."""
    return hashlib.sha256(secret.encode()).hexdigest()
