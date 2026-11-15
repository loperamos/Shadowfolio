"""Order use cases: placing and cancelling orders now, and filling them when market prices allow (see domain.orders).

Orders fill when a wallet's orders are read, and in a job for every wallet. Filling only ever uses prices up to now,
so it is safe to run at any time; a price that cannot be fetched right now leaves the order open for the next try.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import DomainError, InsufficientCashError, InsufficientSharesError
from shadowfolio.domain.orders import Order, OrderSide
from shadowfolio.domain.valuation import Quote
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.wallet_changes import WalletChanges


@dataclass(frozen=True)
class FillSummary:
    wallets: int  # wallets looked at
    filled: int  # orders filled


class Orders:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, changes: WalletChanges) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._changes = changes

    def place(
        self, wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, reason: str = "", limit_price: Decimal | None = None
    ) -> tuple[Wallet, Order] | None:
        """Place an order now, at market or with a limit price; it fills later (see `_fill_due`). Returns the wallet
        and the order, or None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        order = Order(uuid4(), side, symbol.strip().upper(), quantity, self._clock.now(), reason.strip(), limit_price)
        updated = wallet.place_order(order)
        self._repo.update(updated)
        return updated, order

    def cancel(self, wallet_id: UUID, order_id: UUID) -> tuple[Wallet, Order] | None:
        """Cancel an open order. Returns the wallet and the order, or None if the wallet does not exist; an unknown
        order raises OrderNotFoundError."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        order = wallet.order(order_id).cancelled(self._clock.now())
        updated = wallet.with_order(order)
        self._repo.update(updated)
        return updated, order

    def list(self, wallet_id: UUID) -> Wallet | None:
        """The wallet, with its due orders filled first (its orders are on it). None if it does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        filled, _ = self._fill_due(wallet)
        return filled

    def fill_all(self) -> FillSummary:
        """Fill every wallet's due orders. For the job that runs while the market is open."""
        wallets = filled_total = 0
        for wallet_id in self._repo.all_ids():
            wallet = self._repo.get(wallet_id)
            if wallet is None:
                continue
            wallets += 1
            _, filled = self._fill_due(wallet)
            filled_total += filled
        return FillSummary(wallets, filled_total)

    def _fill_due(self, wallet: Wallet) -> tuple[Wallet, int]:
        """Fill each open order whose first price after it is known by now, or reject it when the wallet cannot cover
        it then; save the wallet if anything changed. Returns it and how many orders filled."""
        now = self._clock.now()
        updated, filled = wallet, 0
        for order in (order for order in wallet.orders if order.is_open):
            try:
                quote = self._fill_price(order, now)
            except PriceDataUnavailableError:
                continue  # try again later
            if quote is None:
                continue  # no price after it yet (e.g. the market has not opened since), or its limit not reached
            try:
                traded = self._changes.fill(updated, order.id, order.side, order.symbol, order.quantity, quote)
            except (InsufficientCashError, InsufficientSharesError) as error:
                updated = updated.with_order(order.rejected(quote.as_of, str(error)))
                continue
            except DomainError:
                continue  # e.g. an exchange rate that cannot be fetched right now: try again later
            updated = traded.with_order(order.filled(quote.as_of))
            filled += 1
        if updated is not wallet:
            self._repo.update(updated)
        return updated, filled

    def _fill_price(self, order: Order, now: datetime) -> Quote | None:
        """The price and time an open order fills at, by now; None while it cannot yet."""
        if order.limit_price is None:
            quote = self._prices.price_at(order.symbol, order.placed_at)
            return quote if quote is not None and quote.as_of <= now else None
        # Bars starting at or after the order, so never one already under way when it was placed.
        for bar in self._prices.minute_bars(order.symbol, order.placed_at, now):
            price = order.fill_price(bar)
            if price is not None:
                return Quote(price, bar.currency, bar.as_of)
        return None
