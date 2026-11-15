"""Order use cases: placing and cancelling orders now, and filling them when market prices allow (see domain.orders).

Orders fill when a wallet's orders are read, and in a job for every wallet. Filling only ever uses prices up to now,
so it is safe to run at any time; a price that cannot be fetched right now leaves the order open for the next try.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import (
    DomainError,
    FxRateUnavailableError,
    InsufficientCashError,
    InsufficientSharesError,
    PriceUnavailableError,
)
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.orders import Order, OrderSide
from shadowfolio.domain.valuation import Quote, order_amount, order_price, reserved_for_orders
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallet_changes import WalletChanges


@dataclass(frozen=True)
class OrderEstimate:
    price: Decimal  # what the order is counted at: its limit, or the latest price for a market order
    currency: Currency  # the price's
    fx_rate: FxRate | None  # into the wallet's currency; None when it is the same
    amount: Decimal  # in the wallet's currency, rounded to cents


@dataclass(frozen=True)
class FillSummary:
    wallets: int  # wallets looked at
    filled: int  # orders filled


class Orders:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates, changes: WalletChanges) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._fx_rates = fx_rates
        self._changes = changes
        # The wallet's value now, for its rules.
        self._valuation = Valuation(repo, clock, prices, fx_rates)

    def estimate(
        self, wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, limit_price: Decimal | None = None
    ) -> OrderEstimate | None:
        """What an order would come to if placed now, as the buying power counts it (see domain.valuation): at its
        limit, or a market order at the latest price, at the latest exchange rate. A fill may differ. None if the wallet
        does not exist; fails when there is no price or rate to estimate with."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        order = Order(uuid4(), side, symbol.strip().upper(), quantity, self._clock.now(), limit_price=limit_price)
        quote, rate = self._latest(wallet, order.symbol)
        return OrderEstimate(order_price(order, quote), quote.currency, rate, order_amount(order, quote, rate))

    def _check_value_rules(self, wallet: Wallet, order: Order) -> None:
        """Raise RuleBrokenError if the buy would make a holding too large, or leave too little cash, once it and the
        open buys before it fill, each at its estimate: the open buys of the same symbol count towards the holding."""
        valuation = self._valuation.current(wallet.id)
        assert valuation is not None
        if valuation.buying_power is None:
            raise PriceUnavailableError("could not price the open buys to check the wallet's rules; try again later")
        quote, rate = self._latest(wallet, order.symbol)
        amount = order_amount(order, quote, rate)
        same_symbol = [open_order for open_order in wallet.orders if open_order.symbol == order.symbol]
        reserved = reserved_for_orders(same_symbol, {order.symbol: quote}, {quote.currency: rate} if rate else {}, wallet.currency)
        assert reserved is not None  # the symbol's quote and rate are both given
        held = next((h.value_in_wallet_currency for h in valuation.holdings if h.symbol == order.symbol), Decimal(0))
        wallet.rules.check_buy(order.symbol, valuation.total, held + reserved + amount, valuation.buying_power - amount)

    def _latest(self, wallet: Wallet, symbol: str) -> tuple[Quote, FxRate | None]:
        """The symbol's latest price, and the latest rate into the wallet's currency (None when the same)."""
        try:
            quote = self._prices.latest_prices([symbol]).get(symbol)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        if quote is None:
            raise PriceUnavailableError(f"no price for {symbol}")
        rate = None
        if quote.currency is not wallet.currency:
            try:
                rate = self._fx_rates.latest_rate(quote.currency, wallet.currency)
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(
                    f"could not fetch the {quote.currency}→{wallet.currency} rate right now; try again later"
                ) from error
            if rate is None:
                raise FxRateUnavailableError(f"no {quote.currency}→{wallet.currency} rate")
        return quote, rate

    def place(
        self, wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, reason: str = "", limit_price: Decimal | None = None
    ) -> tuple[Wallet, Order] | None:
        """Place an order now, at market or with a limit price; it fills later (see `_fill_due`). Returns the wallet
        and the order, or None if the wallet does not exist."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        order = Order(uuid4(), side, symbol.strip().upper(), quantity, self._clock.now(), reason.strip(), limit_price)
        wallet.rules.check_order(wallet.orders, order.placed_at)
        if order.side is OrderSide.BUY:
            wallet.rules.check_symbol(order.symbol)
            if wallet.rules.limits_value:
                self._check_value_rules(wallet, order)
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
