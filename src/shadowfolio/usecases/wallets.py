"""Wallet use cases: creating, changing settings (name, withholding tax), copying, deleting and reading wallets."""

from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.wallet_repository import WalletRepository


class Wallets:
    def __init__(self, repo: WalletRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    def create(self, owner_id: str, name: str, currency: Currency, cash: Decimal) -> Wallet:
        """Create a wallet. Non-zero starting cash is recorded as its first deposit."""
        wallet = Wallet(id=uuid4(), owner_id=owner_id, name=name, currency=currency)
        if cash != 0:
            wallet = wallet.deposit(uuid4(), cash, self._clock.now())
        self._repo.add(wallet)
        return wallet

    def update(self, wallet_id: UUID, name: str | None = None, withholding_rate: Decimal | None = None) -> Wallet | None:
        """Change the given settings, leaving the others as they are. Returns None if the wallet does not exist.

        A new withholding rate works out every dividend again; it is refused if the lower cash would not cover the
        withdrawals and buys that followed.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet
        if name is not None:
            updated = updated.rename(name)
        if withholding_rate is not None:
            updated = updated.set_withholding_rate(withholding_rate)
        self._repo.update(updated)
        return updated

    def copy(self, wallet_id: UUID, name: str) -> Wallet | None:
        """A new wallet with the same currency and history under another name. Returns None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        copy = wallet.copy(uuid4(), name, uuid4)
        self._repo.add(copy)
        return copy

    def delete(self, wallet_id: UUID) -> bool:
        """Delete the wallet and its history. Returns False if it does not exist."""
        if self._repo.get(wallet_id) is None:
            return False
        self._repo.delete(wallet_id)
        return True

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._repo.get(wallet_id)

    def list(self, owner_id: str) -> list[Wallet]:
        return self._repo.list_by_owner(owner_id)
