"""Order use cases: placing and cancelling orders now, and filling them when market prices allow (see domain.orders).

Orders fill when a wallet's orders are read, and in a job for every wallet. Filling only ever uses prices up to now,
so it is safe to run at any time; a price that cannot be fetched right now leaves the order open for the next try.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shadowfolio.domain.errors import (
    DomainError,
    FxRateUnavailableError,
    InsufficientCashError,
    InsufficientSharesError,
    PlanLimitError,
    PriceUnavailableError,
    RuleBrokenError,
)
from shadowfolio.domain.money import Currency, FxRate, to_cents
from shadowfolio.domain.operations import Buy, Sell
from shadowfolio.domain.orders import Order, OrderSide, OrderStatus
from shadowfolio.domain.valuation import Quote, order_amount, order_price, reserved_for_orders
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository
from shadowfolio.usecases.comparison import DEFAULT_BENCHMARK
from shadowfolio.usecases.users import Users
from shadowfolio.usecases.valuation import Valuation
from shadowfolio.usecases.wallet_changes import WalletChanges


@dataclass(frozen=True)
class OrderEstimate:
    price: Decimal  # what the order is counted at: its limit, or the latest price for a market order
    currency: Currency  # the price's
    fx_rate: FxRate | None  # into the wallet's currency; None when it is the same
    amount: Decimal  # in the wallet's currency, rounded to cents


@dataclass(frozen=True)
class OrderOutcome:
    """How a filled order turned out since: its symbol's latest price, and the returns from the fill to then of the
    symbol and of a benchmark, each in its own currency (None without a price)."""

    order_id: UUID
    latest: Quote | None
    since_fill: Decimal | None  # as a ratio (0.1 for +10%)
    benchmark_symbol: str
    benchmark_since_fill: Decimal | None


@dataclass(frozen=True)
class OrderPreview:
    """What an order would do if placed now, without placing it: its estimate, the buying power and the holding's
    share of the wallet once it fills (each counted as the buying power counts orders), the rule or plan limit that
    would refuse it,
    and why it would be rejected when it fills (not enough cash or shares)."""

    estimate: OrderEstimate
    buying_power_after: Decimal | None  # None when the open orders cannot all be priced
    holding_weight_after: Decimal | None  # as a ratio of the wallet's whole value; None for an empty wallet
    refusal: str | None  # the wallet's rule or the plan's limit that refuses it now; None when it would be placed
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FillSummary:
    wallets: int  # wallets looked at
    filled: int  # orders filled


class Orders:
    def __init__(
        self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates, changes: WalletChanges, users: Users
    ) -> None:
        self._repo = repo
        self._users = users
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

    def preview(
        self, wallet_id: UUID, side: OrderSide, symbol: str, quantity: Decimal, limit_price: Decimal | None = None
    ) -> OrderPreview | None:
        """What the order would do if placed now (see OrderPreview); nothing is placed. None if the wallet does not
        exist; fails when there is no price or rate to estimate with."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        order = Order(uuid4(), side, symbol.strip().upper(), quantity, self._clock.now(), limit_price=limit_price)
        quote, rate = self._latest(wallet, order.symbol)
        amount = order_amount(order, quote, rate)
        try:
            self._check_plan(wallet)
            self._check_rules(wallet, order)
            refusal = None
        except (PlanLimitError, RuleBrokenError) as error:
            refusal = str(error)
        valuation = self._valuation.current(wallet.id)
        assert valuation is not None
        held = next((h.value_in_wallet_currency for h in valuation.holdings if h.symbol == order.symbol), Decimal(0))
        buying_power = valuation.buying_power
        warnings = []
        if order.side is OrderSide.BUY:
            reserved = self._reserved_for(wallet, order.symbol, quote, rate)
            buying_power_after = None if buying_power is None else buying_power - amount
            holding_after = held + reserved + amount
            if buying_power is not None and buying_power_after is not None and buying_power_after < 0:
                warnings.append(
                    f"it costs {amount} {wallet.currency}, more than the buying power of {to_cents(buying_power)} {wallet.currency}: "
                    "it would be rejected when it fills"
                )
        else:
            buying_power_after = None if buying_power is None else buying_power + amount
            holding_after = max(held - amount, Decimal(0))
            selling = sum(
                (o.quantity for o in wallet.orders if o.is_open and o.side is OrderSide.SELL and o.symbol == order.symbol), Decimal(0)
            )
            shares = wallet.holdings.get(order.symbol, Decimal(0)) - selling
            if order.quantity > shares:
                warnings.append(
                    f"the wallet holds {shares} {order.symbol}, fewer than {order.quantity}: it would be rejected when it fills"
                )
        weight_after = holding_after / valuation.total if valuation.total else None
        estimate = OrderEstimate(order_price(order, quote), quote.currency, rate, amount)
        return OrderPreview(estimate, buying_power_after, weight_after, refusal, tuple(warnings))

    def _check_plan(self, wallet: Wallet) -> None:
        """Raise PlanLimitError if the owner's plan allows no more orders today (UTC), counting every order placed in
        any of their wallets today, cancelled ones too."""
        today = self._clock.now().astimezone(UTC).date()
        placed = sum(
            1
            for owned in self._repo.list_by_owner(wallet.owner_id)
            for order in owned.orders
            if order.placed_at.astimezone(UTC).date() == today
        )
        self._users.user(wallet.owner_id).check_new_order(placed)

    def _check_rules(self, wallet: Wallet, order: Order) -> None:
        """Raise RuleBrokenError if the order breaks one of the wallet's rules (see domain.rules)."""
        wallet.rules.check_order(wallet.orders, order.placed_at)
        if order.side is OrderSide.BUY:
            wallet.rules.check_symbol(order.symbol)
            if wallet.rules.limits_value:
                self._check_value_rules(wallet, order)

    def _reserved_for(self, wallet: Wallet, symbol: str, quote: Quote, rate: FxRate | None) -> Decimal:
        """What the open buys of `symbol` would cost, at `quote` and `rate` (see reserved_for_orders)."""
        same_symbol = [open_order for open_order in wallet.orders if open_order.symbol == symbol]
        reserved = reserved_for_orders(same_symbol, {symbol: quote}, {quote.currency: rate} if rate else {}, wallet.currency)
        assert reserved is not None  # the symbol's quote and rate are both given
        return reserved

    def _check_value_rules(self, wallet: Wallet, order: Order) -> None:
        """Raise RuleBrokenError if the buy would make a holding too large, or leave too little cash, once it and the
        open buys before it fill, each at its estimate: the open buys of the same symbol count towards the holding."""
        valuation = self._valuation.current(wallet.id)
        assert valuation is not None
        if valuation.buying_power is None:
            raise PriceUnavailableError("could not price the open buys to check the wallet's rules; try again later")
        quote, rate = self._latest(wallet, order.symbol)
        amount = order_amount(order, quote, rate)
        reserved = self._reserved_for(wallet, order.symbol, quote, rate)
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
        self._check_plan(wallet)
        self._check_rules(wallet, order)
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

    def outcomes(self, wallet_id: UUID, benchmark: str = DEFAULT_BENCHMARK) -> list[OrderOutcome] | None:
        """How each filled order turned out, against `benchmark` from the same moment: the symbol's return from its fill
        price to its latest, and the benchmark's from its first price at or after the fill to its latest. In the order
        they were placed. None if the wallet does not exist; fails when a price cannot be fetched right now."""
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        benchmark = benchmark.strip().upper()
        trades = {op.id: op.trade for op in wallet.operations if isinstance(op, Buy | Sell)}
        filled = [order for order in wallet.orders if order.status is OrderStatus.FILLED and order.id in trades]
        symbols = sorted({order.symbol for order in filled} | {benchmark})
        try:
            latest = self._prices.latest_prices(symbols) if filled else {}
            benchmark_then = {order.id: self._prices.price_at(benchmark, order.closed_at) for order in filled if order.closed_at}
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the prices of {', '.join(symbols)} right now; try again later") from error
        benchmark_now = latest.get(benchmark)
        outcomes = []
        for order in filled:
            now, then = latest.get(order.symbol), benchmark_then.get(order.id)
            outcomes.append(
                OrderOutcome(
                    order.id,
                    now,
                    None if now is None else now.price / trades[order.id].price - 1,
                    benchmark,
                    None if then is None or benchmark_now is None else benchmark_now.price / then.price - 1,
                )
            )
        return outcomes

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
