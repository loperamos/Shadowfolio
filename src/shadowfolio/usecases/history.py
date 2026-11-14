"""History use cases: recording, correcting and removing what happened in a wallet (cash movements and past trades).

Each loads the wallet, makes one change (see WalletChanges) and saves it. Each returns the updated wallet, or None if
the wallet does not exist; an unknown operation raises OperationNotFoundError.
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates
from shadowfolio.ports.price_data import PriceData
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.sync import Sync
from shadowfolio.usecases.wallet_changes import WalletChanges


class History:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates, sync: Sync) -> None:
        self._repo = repo
        self._changes = WalletChanges(clock, prices, fx_rates, sync)

    # Every recording method can instead replace an existing operation (`replacing=<its id>`), keeping its id.

    def deposit(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Add cash to a wallet, now or at a past timestamp."""
        return self._change(wallet_id, lambda wallet: self._changes.deposit(wallet, amount, timestamp, replacing))

    def withdraw(self, wallet_id: UUID, amount: Decimal, timestamp: datetime | None = None, replacing: UUID | None = None) -> Wallet | None:
        """Take cash out of a wallet, now or at a past timestamp."""
        return self._change(wallet_id, lambda wallet: self._changes.withdraw(wallet, amount, timestamp, replacing))

    def record_buy(
        self,
        wallet_id: UUID,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a buy that already happened: with the price the broker reported, or without one to price it from market data."""
        return self._change(
            wallet_id,
            lambda wallet: self._changes.record_buy(
                wallet, symbol, quantity, timestamp, price, price_currency, settled_amount, fees, replacing
            ),
        )

    def record_sell(
        self,
        wallet_id: UUID,
        symbol: str,
        quantity: Decimal,
        timestamp: datetime,
        price: Decimal | None = None,
        price_currency: Currency | None = None,
        settled_amount: Decimal | None = None,
        fees: Decimal = Decimal(0),
        replacing: UUID | None = None,
    ) -> Wallet | None:
        """Record a sell that already happened: with the price the broker reported, or without one to price it from market data."""
        return self._change(
            wallet_id,
            lambda wallet: self._changes.record_sell(
                wallet, symbol, quantity, timestamp, price, price_currency, settled_amount, fees, replacing
            ),
        )

    def delete_operation(self, wallet_id: UUID, operation_id: UUID) -> Wallet | None:
        """Remove an operation; the rest of the history must still hold together."""
        return self._change(wallet_id, lambda wallet: wallet.remove_operation(operation_id))

    def _change(self, wallet_id: UUID, change: Callable[[Wallet], Wallet]) -> Wallet | None:
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        updated = change(wallet)
        self._repo.update(updated)
        return updated
