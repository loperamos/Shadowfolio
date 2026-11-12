"""Wallet use cases: creating wallets and reading them."""

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

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._repo.get(wallet_id)

    def list(self, owner_id: str) -> list[Wallet]:
        return self._repo.list_by_owner(owner_id)
