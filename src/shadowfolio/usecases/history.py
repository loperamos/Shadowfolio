"""History use cases: recording what happened in a wallet (cash movements and past trades).

Each returns the updated wallet, or None if the wallet does not exist.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import FutureTimestampError
from shadowfolio.domain.operations import Trade
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.wallet_repository import WalletRepository


class History:
    def __init__(self, repo: WalletRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    def deposit(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None) -> Wallet | None:
        """Add cash to a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.deposit(uuid4(), amount, self._at(timestamp))
        self._repo.update(updated)
        return updated

    def withdraw(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None) -> Wallet | None:
        """Take cash out of a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.withdraw(uuid4(), amount, self._at(timestamp))
        self._repo.update(updated)
        return updated

    def record_buy(
        self, wallet_id: UUID, trade: Trade, timestamp: datetime, settled_amount: Decimal | None = None, fees: Decimal = Decimal(0)
    ) -> Wallet | None:
        """Record a buy that already happened, with the price the broker reported."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.buy(uuid4(), trade, self._at(timestamp), settled_amount, fees)
        self._repo.update(updated)
        return updated

    def record_sell(
        self, wallet_id: UUID, trade: Trade, timestamp: datetime, settled_amount: Decimal | None = None, fees: Decimal = Decimal(0)
    ) -> Wallet | None:
        """Record a sell that already happened, with the price the broker reported."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.sell(uuid4(), trade, self._at(timestamp), settled_amount, fees)
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
