"""AccessTokenRepository in memory, for tests."""

from uuid import UUID

from shadowfolio.domain.access import AccessToken
from shadowfolio.ports.access_token_repository import AccessTokenRepository


class InMemoryAccessTokenRepository(AccessTokenRepository):
    def __init__(self) -> None:
        self._tokens: dict[UUID, AccessToken] = {}  # in the order they were added

    def add(self, token: AccessToken) -> None:
        self._tokens[token.id] = token

    def update(self, token: AccessToken) -> None:
        self._tokens[token.id] = token

    def get(self, token_id: UUID) -> AccessToken | None:
        return self._tokens.get(token_id)

    def find_by_hash(self, secret_hash: str) -> AccessToken | None:
        return next((token for token in self._tokens.values() if token.secret_hash == secret_hash), None)

    def list_by_owner(self, owner_id: str) -> list[AccessToken]:
        return [token for token in self._tokens.values() if token.owner_id == owner_id]

    def delete(self, token_id: UUID) -> None:
        self._tokens.pop(token_id, None)
