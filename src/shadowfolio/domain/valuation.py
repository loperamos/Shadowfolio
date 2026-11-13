"""Valuation: what a wallet is worth, in its own currency, given market prices and exchange rates."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.wallet import Wallet

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Quote:
    """A market price for one share, in the listing's currency, as of a time, with the previous trading day's close."""

    price: Decimal
    currency: Currency
    as_of: datetime
    previous_close: Decimal | None = None  # None when the provider has none (e.g. a new listing)


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
        """Worth of the holding in the wallet's currency; converted values are rounded to cents."""
        if self.fx_rate is None:
            return self.value
        return (self.value * self.fx_rate.rate).quantize(CENT, rounding=ROUND_HALF_EVEN)

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
        return change if self.fx_rate is None else (change * self.fx_rate.rate).quantize(CENT, rounding=ROUND_HALF_EVEN)

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
