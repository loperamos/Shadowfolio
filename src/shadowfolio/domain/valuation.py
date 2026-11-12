"""Valuation: what a wallet is worth, given market prices. No FX yet, so values stay in each price's currency."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from shadowfolio.domain.money import Currency
from shadowfolio.domain.wallet import Wallet


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
    quote: Quote

    @property
    def value(self) -> Decimal:
        """Worth of the holding, in the quote's currency."""
        return self.quantity * self.quote.price


@dataclass(frozen=True)
class WalletValuation:
    cash: Decimal
    cash_currency: Currency
    holdings: tuple[HoldingValue, ...]  # sorted by symbol

    @property
    def totals(self) -> dict[Currency, Decimal]:
        """Cash plus holdings, summed per currency. Different currencies are not added together."""
        totals = {self.cash_currency: self.cash}
        for holding in self.holdings:
            currency = holding.quote.currency
            totals[currency] = totals.get(currency, Decimal(0)) + holding.value
        return totals


def value_wallet(wallet: Wallet, quotes: Mapping[str, Quote]) -> WalletValuation:
    """Value the wallet's current holdings. `quotes` must have a quote for every symbol held."""
    holdings = tuple(HoldingValue(symbol, quantity, quotes[symbol]) for symbol, quantity in sorted(wallet.holdings.items()))
    return WalletValuation(cash=wallet.cash, cash_currency=wallet.currency, holdings=holdings)
