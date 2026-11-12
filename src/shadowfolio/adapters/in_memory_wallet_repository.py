"""WalletRepository kept in memory, for tests and running locally without a database."""

from uuid import UUID

from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.wallet_repository import WalletRepository


class InMemoryWalletRepository(WalletRepository):
    def __init__(self) -> None:
        self._wallets: dict[UUID, Wallet] = {}

    def add(self, wallet: Wallet) -> None:
        self._wallets[wallet.id] = wallet

    def update(self, wallet: Wallet) -> None:
        self._wallets[wallet.id] = wallet

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._wallets.get(wallet_id)

    def delete(self, wallet_id: UUID) -> None:
        self._wallets.pop(wallet_id, None)

    def list_by_owner(self, owner_id: str) -> list[Wallet]:
        return [wallet for wallet in self._wallets.values() if wallet.owner_id == owner_id]
