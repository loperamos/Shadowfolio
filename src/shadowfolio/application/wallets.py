"""Wallet use cases."""

from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.wallet import Currency, Wallet
from shadowfolio.ports.wallet_repository import WalletRepository


def create_wallet(
    repo: WalletRepository, owner_id: str, name: str, currency: Currency, cash: Decimal
) -> Wallet:
    wallet = Wallet(id=uuid4(), owner_id=owner_id, name=name, currency=currency, cash=cash)
    repo.add(wallet)
    return wallet


def get_wallet(repo: WalletRepository, wallet_id: UUID) -> Wallet | None:
    return repo.get(wallet_id)
