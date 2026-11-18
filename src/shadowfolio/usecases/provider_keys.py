"""Use cases for a user's own market-data keys: saving, listing and removing them."""

from shadowfolio.domain.provider_keys import NAMES, NEEDED, DataProvider, KeyCheck, ProviderKey
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.key_checker import KeyChecker
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository
from shadowfolio.usecases.users import Users


class ProviderKeys:
    def __init__(self, repo: ProviderKeyRepository, clock: Clock, users: Users, checker: KeyChecker) -> None:
        self._repo = repo
        self._checker = checker
        self._clock = clock
        self._users = users

    def save(self, owner_id: str, provider: DataProvider, key_id: str | None, secret: str) -> ProviderKey:
        """Save the owner's key for the provider, replacing any earlier one; spaces around each part are dropped."""
        key = ProviderKey(owner_id, provider, (key_id or "").strip() or None, secret.strip(), self._clock.now())
        self._repo.save(key)
        return key

    def missing(self, user_id: str) -> list[DataProvider]:
        """The providers whose key the user still needs to connect for market data; none for those who may use the
        server's own keys."""
        if self._users.user(user_id).uses_server_keys:
            return []
        return [provider for provider in NEEDED if self._repo.get(user_id, provider) is None]

    def list(self, owner_id: str) -> list[ProviderKey]:
        return self._repo.list_by_owner(owner_id)

    def test(self, owner_id: str, provider: DataProvider) -> KeyCheck | None:
        """Whether the owner's saved key for the provider works, asking the provider; None if they saved none."""
        key = self._repo.get(owner_id, provider)
        if key is None:
            return None
        reason = self._checker.check(key)
        return KeyCheck(True, f"{NAMES[provider]} answered with this key.") if reason is None else KeyCheck(False, reason)

    def delete(self, owner_id: str, provider: DataProvider) -> bool:
        """Forget the owner's key for the provider; False if they had none."""
        return self._repo.delete(owner_id, provider)
