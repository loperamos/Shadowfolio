"""Persistence for wallets."""

from typing import Protocol
from uuid import UUID

from shadowfolio.domain.wallet import Wallet


class WalletRepository(Protocol):
    def add(self, wallet: Wallet) -> None: ...

    def get(self, wallet_id: UUID) -> Wallet | None: ...
