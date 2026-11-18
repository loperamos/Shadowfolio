"""Use cases for a user's own market-data keys: saving, listing and removing them."""

from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository


class ProviderKeys:
    def __init__(self, repo: ProviderKeyRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    def save(self, owner_id: str, provider: DataProvider, key_id: str | None, secret: str) -> ProviderKey:
        """Save the owner's key for the provider, replacing any earlier one; spaces around each part are dropped."""
        key = ProviderKey(owner_id, provider, (key_id or "").strip() or None, secret.strip(), self._clock.now())
        self._repo.save(key)
        return key

    def list(self, owner_id: str) -> list[ProviderKey]:
        return self._repo.list_by_owner(owner_id)

    def delete(self, owner_id: str, provider: DataProvider) -> bool:
        """Forget the owner's key for the provider; False if they had none."""
        return self._repo.delete(owner_id, provider)
