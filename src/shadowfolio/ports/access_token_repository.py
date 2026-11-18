"""Persistence for access tokens."""

from abc import ABC, abstractmethod
from uuid import UUID

from shadowfolio.domain.access import AccessToken


class AccessTokenRepository(ABC):
    @abstractmethod
    def add(self, token: AccessToken) -> None: ...

    @abstractmethod
    def update(self, token: AccessToken) -> None:
        """Store the token's current state (e.g. when it was last used, or revoked)."""

    @abstractmethod
    def get(self, token_id: UUID) -> AccessToken | None: ...

    @abstractmethod
    def find_by_hash(self, secret_hash: str) -> AccessToken | None:
        """The token whose secret has this hash, revoked or not."""

    @abstractmethod
    def list_by_owner(self, owner_id: str) -> list[AccessToken]:
        """The owner's tokens, in the order they were added."""

    @abstractmethod
    def delete(self, token_id: UUID) -> None:
        """Forget the token (e.g. with its owner's account); nothing if there is none."""
