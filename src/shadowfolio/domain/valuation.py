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
    """A market price for one share, in the listing's currency, as of a time."""

    price: Decimal
    currency: Currency
    as_of: datetime


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
