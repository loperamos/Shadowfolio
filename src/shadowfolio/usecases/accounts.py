"""Account use cases: deleting a user's account, with everything that is theirs."""

from shadowfolio.domain.provider_keys import DataProvider
from shadowfolio.ports.access_token_repository import AccessTokenRepository
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository
from shadowfolio.ports.user_repository import UserRepository
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.usage import Usage


class Accounts:
    def __init__(
        self, users: UserRepository, wallets: WalletRepository, tokens: AccessTokenRepository, keys: ProviderKeyRepository, usage: Usage
    ) -> None:
        self._users = users
        self._wallets = wallets
        self._tokens = tokens
        self._keys = keys
        self._usage = usage

    def delete(self, user_id: str) -> None:
        """Delete the user's account: their wallets (with their history and orders), agent tokens (their agents stop
        at once), market-data keys, usage counts, and the account itself. Signing in again starts a new, empty one."""
        for token in self._tokens.list_by_owner(user_id):
            self._tokens.delete(token.id)
        for wallet in self._wallets.list_by_owner(user_id):
            self._wallets.delete(wallet.id)
        for provider in DataProvider:
            self._keys.delete(user_id, provider)
        self._usage.forget(user_id)
        self._users.delete(user_id)
