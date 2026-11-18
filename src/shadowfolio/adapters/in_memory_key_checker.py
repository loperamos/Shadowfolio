"""KeyChecker from a table of refused secrets, for tests: every other key works."""

from collections.abc import Mapping

from shadowfolio.domain.provider_keys import ProviderKey
from shadowfolio.ports.key_checker import KeyChecker


class InMemoryKeyChecker(KeyChecker):
    def __init__(self, refused: Mapping[str, str] | None = None) -> None:
        """`refused` maps the secrets that do not work to why."""
        self._refused = dict(refused or {})

    def check(self, key: ProviderKey) -> str | None:
        return self._refused.get(key.secret)
