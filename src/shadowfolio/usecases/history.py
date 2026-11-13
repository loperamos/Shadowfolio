"""History use cases: recording, correcting and removing what happened in a wallet (cash movements and past trades).

Each returns the updated wallet, or None if the wallet does not exist; an unknown operation raises OperationNotFoundError.
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

    # Every recording method can instead replace an existing operation (`replacing=<its id>`), keeping its id.

    def deposit(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Add cash to a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.deposit(replacing or uuid4(), amount, self._at(timestamp), replacing)
        self._repo.update(updated)
        return updated

    def withdraw(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Take cash out of a wallet, now or at a past timestamp."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.withdraw(replacing or uuid4(), amount, self._at(timestamp), replacing)
        self._repo.update(updated)
        return updated

    def record_buy(
        self,
        wallet_id: UUID,
        trade: Trade,
        timestamp: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a buy that already happened, with the price the broker reported."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.buy(replacing or uuid4(), trade, self._at(timestamp), settled_amount, fees, replacing)
        self._repo.update(updated)
        return updated

    def record_sell(
        self,
        wallet_id: UUID,
        trade: Trade,
        timestamp: datetime,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a sell that already happened, with the price the broker reported."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.sell(replacing or uuid4(), trade, self._at(timestamp), settled_amount, fees, replacing)
        self._repo.update(updated)
        return updated

    def delete_operation(self, wallet_id: UUID, operation_id: UUID) -> Wallet | None:
        """Remove an operation; the rest of the history must still hold together."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = wallet.remove_operation(operation_id)
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
