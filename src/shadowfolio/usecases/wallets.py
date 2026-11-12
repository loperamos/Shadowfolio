"""Wallet use cases."""

from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.wallet import Currency, Wallet
from shadowfolio.ports.wallet_repository import WalletRepository


class Wallets:
    def __init__(self, repo: WalletRepository) -> None:
        self._repo = repo

    def create(self, owner_id: str, name: str, currency: Currency, cash: Decimal) -> Wallet:
        wallet = Wallet(id=uuid4(), owner_id=owner_id, name=name, currency=currency, cash=cash)
        self._repo.add(wallet)
        return wallet

    def get(self, wallet_id: UUID) -> Wallet | None:
        return self._repo.get(wallet_id)
