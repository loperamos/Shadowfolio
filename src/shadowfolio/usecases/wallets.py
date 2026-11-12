"""Wallet use cases."""

from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.wallet import Currency, Wallet
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

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._repo.get(wallet_id)

    def deposit(self, wallet_id: UUID, amount: Decimal) -> Wallet | None:
        """Add cash to a wallet. Returns None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.deposit(uuid4(), amount, self._clock.now())
        self._repo.update(updated)
        return updated
