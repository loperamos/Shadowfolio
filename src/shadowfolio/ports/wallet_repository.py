"""Persistence for wallets."""

from abc import ABC, abstractmethod
from uuid import UUID

from shadowfolio.domain.wallet import Wallet


class WalletRepository(ABC):
    @abstractmethod
    def add(self, wallet: Wallet) -> None: ...

    @abstractmethod
    def get(self, wallet_id: UUID) -> Wallet | None: ...
