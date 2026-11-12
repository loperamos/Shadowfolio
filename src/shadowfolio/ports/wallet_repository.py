"""Persistence for wallets, together with their operations."""

from abc import ABC, abstractmethod
from uuid import UUID

from shadowfolio.domain.wallet import Wallet


class WalletRepository(ABC):
    @abstractmethod
    def add(self, wallet: Wallet) -> None: ...

    @abstractmethod
    def update(self, wallet: Wallet) -> None:
        """Store the wallet's current state, including operations added since it was loaded."""

    @abstractmethod
    def get(self, wallet_id: UUID) -> Wallet | None:
        """The wallet with its operations, oldest first."""

    @abstractmethod
    def list_by_owner(self, owner_id: str) -> list[Wallet]:
        """The owner's wallets, in the order they were added."""
