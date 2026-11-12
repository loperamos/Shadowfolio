"""Wallet use cases."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.wallet import Currency, FutureTimestampError, Trade, Wallet
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

    def deposit(
        self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None
    ) -> Wallet | None:
        """Add cash to a wallet, now or at a past timestamp.

        Returns None if the wallet does not exist.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.deposit(uuid4(), amount, self._at(timestamp))
        self._repo.update(updated)
        return updated

    def withdraw(self, wallet_id: UUID, amount: Decimal) -> Wallet | None:
        """Take cash out of a wallet now. Returns None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.withdraw(uuid4(), amount, self._clock.now())
        self._repo.update(updated)
        return updated

    def record_buy(
        self,
        wallet_id: UUID,
        trade: Trade,
        timestamp: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
    ) -> Wallet | None:
        """Record a buy that already happened, with the price the broker reported.

        Returns None if the wallet does not exist.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.buy(uuid4(), trade, self._at(timestamp), settled_amount, fees)
        self._repo.update(updated)
        return updated

    def _at(self, timestamp: datetime | None) -> datetime:
        """The operation's time: now if not given; a given time must not be in the future."""
        now = self._clock.now()
        if timestamp is None:
            return now
        if timestamp > now:
            raise FutureTimestampError("operations cannot be dated in the future")
        return timestamp
