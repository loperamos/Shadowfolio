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
