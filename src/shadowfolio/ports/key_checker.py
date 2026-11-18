"""Checking a user's market-data key with its provider, as they save or test it."""

from abc import ABC, abstractmethod

from shadowfolio.domain.provider_keys import ProviderKey


class KeyChecker(ABC):
    @abstractmethod
    def check(self, key: ProviderKey) -> str | None:
        """None when the provider answers with the key; otherwise why not, in words to show its owner (never the key)."""
