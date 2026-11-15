"""Valuation: what a wallet is worth, in its own currency, given market prices and exchange rates."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from shadowfolio.domain.money import Currency, FxRate, to_cents
from shadowfolio.domain.operations import Buy, Operation, Sell
from shadowfolio.domain.orders import Order, OrderSide
from shadowfolio.domain.wallet import Wallet


@dataclass(frozen=True)
class Quote:
    """A market price for one share, in the listing's currency, as of a time, with the previous trading day's close."""

    price: Decimal
    currency: Currency
    as_of: datetime
    previous_close: Decimal | None = None  # None when the provider has none (e.g. a new listing)

    @property
    def change(self) -> Decimal | None:
        """How much the price moved since the previous close; None without one."""
        return None if self.previous_close is None else self.price - self.previous_close

    @property
    def change_ratio(self) -> Decimal | None:
        """That move against the previous close (0.0185 for +1.85%); None without one."""
        return None if self.change is None or not self.previous_close else self.change / self.previous_close


@dataclass(frozen=True)
class HoldingValue:
    symbol: str
    quantity: Decimal
    cost: Decimal  # what the shares held cost, in the wallet's currency (FIFO, fees included)
    quote: Quote
    fx_rate: FxRate | None  # from the quote's currency into the wallet's; None when they are the same

    @property
    def value(self) -> Decimal:
        """Worth of the holding, in the quote's currency."""
        return self.quantity * self.quote.price

    @property
    def value_in_wallet_currency(self) -> Decimal:
        """Worth of the holding in the wallet's currency, rounded to cents."""
        return to_cents(self.value if self.fx_rate is None else self.value * self.fx_rate.rate)

    @property
    def gain(self) -> Decimal:
        """Unrealized gain (negative for a loss), in the wallet's currency."""
        return self.value_in_wallet_currency - self.cost

    @property
    def day_change(self) -> Decimal | None:
        """How much the holding's value moved since the previous close, in the wallet's currency.

        From the price only, converted at the current rate; exchange-rate moves are not included. Shares bought today
        are also compared with the previous close.
        """
        if self.quote.previous_close is None:
            return None
        change = self.quantity * (self.quote.price - self.quote.previous_close)
        return to_cents(change if self.fx_rate is None else change * self.fx_rate.rate)

    @property
    def day_change_ratio(self) -> Decimal | None:
        """The price's move since the previous close, as a fraction of it."""
        if not self.quote.previous_close:
            return None
        return (self.quote.price - self.quote.previous_close) / self.quote.previous_close


@dataclass(frozen=True)
class WalletValuation:
    currency: Currency
    cash: Decimal
    holdings: tuple[HoldingValue, ...]  # sorted by symbol
    # What open buy orders would cost (see `reserved_for_orders`); None when unknown, or for a past day.
    reserved_for_orders: Decimal | None = None

    @property
    def cost(self) -> Decimal:
        """What the holdings cost, in the wallet's currency."""
        return sum((h.cost for h in self.holdings), Decimal(0))

    @property
    def gain(self) -> Decimal:
        """Unrealized gain of all holdings, in the wallet's currency."""
        return sum((h.gain for h in self.holdings), Decimal(0))

    @property
    def day_change(self) -> Decimal | None:
        """How much the holdings moved since the previous close; None if any holding has no previous close."""
        changes = [h.day_change for h in self.holdings]
        if not changes or any(change is None for change in changes):
            return None
        return sum((change for change in changes if change is not None), Decimal(0))

    @property
    def day_change_ratio(self) -> Decimal | None:
        """The day change as a fraction of what the holdings were worth at the previous close."""
        change = self.day_change
        if change is None:
            return None
        previous_value = sum((h.value_in_wallet_currency for h in self.holdings), Decimal(0)) - change
        return change / previous_value if previous_value else None

    @property
    def total(self) -> Decimal:
        """Cash plus all holdings, in the wallet's currency."""
        return self.cash + sum((h.value_in_wallet_currency for h in self.holdings), Decimal(0))

    @property
    def buying_power(self) -> Decimal | None:
        """Cash not yet committed to open buy orders: what new buys can still spend. None when that is unknown."""
        return None if self.reserved_for_orders is None else self.cash - self.reserved_for_orders

    def weight(self, holding: HoldingValue) -> Decimal | None:
        """The holding's share of the wallet's whole value, cash included (0.31 for 31%); None for an empty wallet."""
        return holding.value_in_wallet_currency / self.total if self.total else None

    @property
    def cash_weight(self) -> Decimal | None:
        """Cash's share of the wallet's whole value; None for an empty wallet."""
        return self.cash / self.total if self.total else None

    @property
    def largest_weight(self) -> Decimal | None:
        """The largest holding's share of the wallet's whole value; None without holdings."""
        weights = [weight for holding in self.holdings if (weight := self.weight(holding)) is not None]
        return max(weights) if weights else None

    @property
    def effective_holdings(self) -> Decimal | None:
        """How many equal-sized holdings the holdings spread risk like: 1 / the sum of their squared shares of what is
        invested (the inverse Herfindahl index). Ten equal holdings give 10; one at 90% and nine small ones about 1.2.
        None without holdings worth anything."""
        invested = sum((h.value_in_wallet_currency for h in self.holdings), Decimal(0))
        if invested <= 0:
            return None
        return 1 / sum(((h.value_in_wallet_currency / invested) ** 2 for h in self.holdings), Decimal(0))


@dataclass(frozen=True)
class DailyValue:
    """The wallet at the end of a day, valued at that day's closes, with the money put in up to then. A holding
    market data has no prices for is valued at an estimated price (see `estimated_price`), and `estimated` says which. `total`
    is None when a holding has no price at all that day, or its currency no rate: `missing` says which (a symbol, or
    e.g. "USD→EUR")."""

    day: date
    total: Decimal | None  # cash plus the holdings' value, in the wallet's currency
    cash: Decimal
    net_deposits: Decimal
    missing: tuple[str, ...] = ()
    estimated: tuple[str, ...] = ()


def estimated_price(operations: Iterable[Operation], symbol: str, day: date) -> Quote | None:
    """A price standing in for a missing close of `symbol` on `day` (e.g. a listing market data does not cover): that
    of the wallet's last trade in it on or before that day, else of its next one (e.g. shares received without a
    price, sold later). None when the wallet never traded it. Operations are oldest first."""
    trades = [op for op in operations if isinstance(op, Buy | Sell) and op.trade.symbol == symbol]
    before = [op for op in trades if op.timestamp.astimezone(UTC).date() <= day]
    nearest = before[-1] if before else next(iter(trades), None)
    return None if nearest is None else Quote(nearest.trade.price, nearest.trade.price_currency, nearest.timestamp)


def holdings_value(
    holdings: Mapping[str, Decimal], quotes: Mapping[str, Quote], rates: Mapping[Currency, FxRate], currency: Currency
) -> Decimal:
    """What `holdings` (shares per symbol) are worth in `currency`, each rounded to cents as in a valuation (see
    HoldingValue). `quotes` must have every symbol, and `rates` every other currency they are quoted in."""
    total = Decimal(0)
    for symbol, quantity in holdings.items():
        quote = quotes[symbol]
        value = quantity * quote.price
        total += to_cents(value if quote.currency is currency else value * rates[quote.currency].rate)
    return total


def value_wallet(wallet: Wallet, quotes: Mapping[str, Quote], rates: Mapping[Currency, FxRate]) -> WalletValuation:
    """Value the wallet's current holdings.

    `quotes` must have a quote for every symbol held, and `rates` a rate from every quote currency
    other than the wallet's into the wallet's currency.
    """
    positions = wallet.ledger.positions
    holdings = tuple(
        HoldingValue(
            symbol,
            quantity,
            positions[symbol].cost,
            quotes[symbol],
            None if quotes[symbol].currency is wallet.currency else rates[quotes[symbol].currency],
        )
        for symbol, quantity in sorted(wallet.holdings.items())
    )
    return WalletValuation(currency=wallet.currency, cash=wallet.cash, holdings=holdings)


def reserved_for_orders(
    orders: Iterable[Order], quotes: Mapping[str, Quote], rates: Mapping[Currency, FxRate], currency: Currency
) -> Decimal | None:
    """What the open buy orders among `orders` would cost, in `currency`: each at its limit price, or a market order at
    its symbol's quote, converted at `rates` and rounded to cents per order, as a fill would be. None when an order's
    symbol has no quote, or its currency no rate."""
    total = Decimal(0)
    for order in orders:
        if not order.is_open or order.side is not OrderSide.BUY:
            continue
        quote = quotes.get(order.symbol)
        if quote is None:
            return None
        cost = order.quantity * (quote.price if order.limit_price is None else order.limit_price)
        if quote.currency is not currency:
            rate = rates.get(quote.currency)
            if rate is None:
                return None
            cost *= rate.rate
        total += to_cents(cost)
    return total
