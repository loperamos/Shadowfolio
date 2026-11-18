"""Persistence for users' market-data keys: at most one per user and provider. Keys are secrets: a real store keeps
them encrypted."""

from abc import ABC, abstractmethod

from shadowfolio.domain.provider_keys import DataProvider, ProviderKey


class ProviderKeyRepository(ABC):
    @abstractmethod
    def save(self, key: ProviderKey) -> None:
        """Store the key, replacing its owner's earlier one for the same provider."""

    @abstractmethod
    def get(self, owner_id: str, provider: DataProvider) -> ProviderKey | None: ...

    @abstractmethod
    def list_by_owner(self, owner_id: str) -> list[ProviderKey]: ...

    @abstractmethod
    def delete(self, owner_id: str, provider: DataProvider) -> bool:
        """Forget the key; False if there was none."""
