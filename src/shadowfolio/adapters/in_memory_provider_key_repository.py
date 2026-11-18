"""ProviderKeyRepository in memory, for tests."""

from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository


class InMemoryProviderKeyRepository(ProviderKeyRepository):
    def __init__(self) -> None:
        self._keys: dict[tuple[str, DataProvider], ProviderKey] = {}

    def save(self, key: ProviderKey) -> None:
        self._keys[(key.owner_id, key.provider)] = key

    def get(self, owner_id: str, provider: DataProvider) -> ProviderKey | None:
        return self._keys.get((owner_id, provider))

    def list_by_owner(self, owner_id: str) -> list[ProviderKey]:
        return [key for (owner, _), key in self._keys.items() if owner == owner_id]

    def delete(self, owner_id: str, provider: DataProvider) -> bool:
        return self._keys.pop((owner_id, provider), None) is not None
