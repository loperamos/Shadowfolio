"""Valuation use cases: what a wallet is worth at market prices, in its own currency, now or at the end of a past day."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from shadowfolio.domain.errors import FutureTimestampError, FxRateUnavailableError, InvalidPeriodError, PriceUnavailableError
from shadowfolio.domain.money import Currency, FxRate
from shadowfolio.domain.operations import Buy, Sell
from shadowfolio.domain.orders import OrderSide
from shadowfolio.domain.valuation import (
    DailyValue,
    Quote,
    WalletValuation,
    estimated_price,
    holding_values,
    reserved_for_orders,
    value_wallet,
)
from shadowfolio.domain.wallet import Wallet
from shadowfolio.ports.clock import Clock
from shadowfolio.ports.fx_rates import FxRates, FxRatesUnavailableError
from shadowfolio.ports.price_data import PriceData, PriceDataUnavailableError
from shadowfolio.ports.wallet_repository import WalletRepository


class Valuation:
    def __init__(self, repo: WalletRepository, clock: Clock, prices: PriceData, fx_rates: FxRates) -> None:
        self._repo = repo
        self._clock = clock
        self._prices = prices
        self._fx_rates = fx_rates

    def current(self, wallet_id: UUID) -> WalletValuation | None:
        """The wallet valued at the latest prices and exchange rates. Returns None if the wallet does not exist.

        Fails if any held symbol has no price, or any needed currency has no rate, rather than returning a partial value.
        """
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        # Every holding's price in one go, rather than one request after another; with those of open buy orders, for
        # what they would cost.
        buying = {order.symbol for order in wallet.orders if order.is_open and order.side is OrderSide.BUY}
        symbols = sorted(set(wallet.holdings) | buying)
        try:
            quotes = self._prices.latest_prices(symbols)
        except PriceDataUnavailableError as error:
            raise PriceUnavailableError(f"could not fetch the price of {', '.join(symbols)} right now; try again later") from error
        valuation = self._value(wallet, quotes.get, lambda currency: self._fx_rates.latest_rate(currency, wallet.currency), "")
        rates = {h.quote.currency: h.fx_rate for h in valuation.holdings if h.fx_rate is not None}
        for currency in {quotes[symbol].currency for symbol in buying if symbol in quotes} - set(rates) - {wallet.currency}:
            try:
                rate = self._fx_rates.latest_rate(currency, wallet.currency)
            except FxRatesUnavailableError:
                continue  # what the orders would cost is then unknown
            if rate is not None:
                rates[currency] = rate
        return replace(valuation, reserved_for_orders=reserved_for_orders(wallet.orders, quotes, rates, wallet.currency))

    def on(self, wallet_id: UUID, day: date) -> WalletValuation | None:
        """The wallet as it was at the end of `day` (every operation dated that day, in UTC, included), valued at that
        day's closing prices and exchange rates, or the last ones before it (weekends, holidays). Returns None if the
        wallet does not exist. Fails the same way as `current`, and for a day after today.
        """
        if day > self._clock.now().date():
            raise FutureTimestampError("cannot value a wallet on a day that has not happened yet")
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        past = wallet.as_of(_end_of(day))
        return self._value(
            past,
            lambda symbol: self._prices.close_on(symbol, day),
            lambda currency: self._fx_rates.rate_on(currency, wallet.currency, day),
            f" on or before {day.isoformat()}",
        )

    def daily(self, wallet_id: UUID, start: date | None = None, end: date | None = None) -> list[DailyValue] | None:
        """The wallet's value at the end of every day from `start` (default: its first operation's day) to `end`
        (default: today), as `on` would give each, with one price request per symbol and one rate request per currency.

        Returns None if the wallet does not exist, and an empty list if it has no operations. A holding market data has
        no prices for at all is valued at the price of the wallet's nearest trade in it, and the day says so; a day
        still without a price for a holding, or a rate for its currency, is left unvalued and says what is missing.
        Fails, as a whole, when a provider cannot answer, or for a period that ends before it starts.
        """
        today = self._clock.now().date()
        wallet = self._repo.get(wallet_id)
        if wallet is None:
            return None
        if not wallet.operations:
            return []
        start = start or wallet.operations[0].timestamp.astimezone(UTC).date()
        end = end or today
        if end > today:
            raise FutureTimestampError("cannot value a wallet on a day that has not happened yet")
        if end < start:
            raise InvalidPeriodError("the period must not end before it starts")
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        # Each day's state in one pass over the operations, rather than rebuilding the wallet for every day.
        states = wallet.states_at([_end_of(day) for day in days])
        closes: dict[str, dict[date, Quote]] = {}
        for symbol in sorted({symbol for state in states for symbol in state.holdings}):
            try:
                closes[symbol] = self._prices.closes_between(symbol, start, end)
            except PriceDataUnavailableError as error:
                raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
        # Symbols market data has no prices for at all (e.g. listings it does not cover) are valued at the price of the
        # wallet's nearest trade in them; days before a covered symbol's history starts are left unvalued.
        trades = {
            symbol: [op for op in wallet.operations if isinstance(op, Buy | Sell) and op.trade.symbol == symbol]
            for symbol, by_day in closes.items()
            if not by_day
        }
        quoted_in = {close.currency for by_day in closes.values() for close in by_day.values()}
        quoted_in |= {op.trade.price_currency for by_symbol in trades.values() for op in by_symbol}
        rates: dict[Currency, dict[date, FxRate]] = {}
        for currency in quoted_in - {wallet.currency}:
            try:
                rates[currency] = self._fx_rates.rates_between(currency, wallet.currency, start, end)
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(f"could not fetch the {currency}→{wallet.currency} rate right now; try again later") from error
        values = []
        for day, state in zip(days, states, strict=True):
            day_closes = {symbol: by_day[day] for symbol, by_day in closes.items() if day in by_day and symbol in state.holdings}
            estimated = []
            for symbol in sorted(set(state.holdings) & set(trades)):
                quote = estimated_price(trades[symbol], symbol, day)
                if quote is not None:
                    day_closes[symbol] = quote
                    estimated.append(symbol)
            day_rates = {currency: by_day[day] for currency, by_day in rates.items() if day in by_day}
            missing = [symbol for symbol in sorted(state.holdings) if symbol not in day_closes]
            currencies = sorted({close.currency for close in day_closes.values()} - {wallet.currency} - set(day_rates))
            missing += [f"{currency}→{wallet.currency}" for currency in currencies]
            worth = {} if missing else holding_values(state.holdings, day_closes, day_rates, wallet.currency)
            total = None if missing else state.cash + sum(worth.values(), Decimal(0))
            values.append(DailyValue(day, total, state.cash, state.net_deposits, tuple(missing), tuple(estimated), worth))
        return values

    def _value(
        self,
        wallet: Wallet,
        quote_of: Callable[[str], Quote | None],
        rate_of: Callable[[Currency], FxRate | None],
        when: str,  # added to messages, e.g. " on or before 2024-06-24"
    ) -> WalletValuation:
        quotes: dict[str, Quote] = {}
        for symbol in wallet.holdings:
            try:
                quote = quote_of(symbol)
            except PriceDataUnavailableError as error:
                raise PriceUnavailableError(f"could not fetch the price of {symbol} right now; try again later") from error
            if quote is None:
                raise PriceUnavailableError(f"no price for {symbol}{when}")
            quotes[symbol] = quote
        rates: dict[Currency, FxRate] = {}
        for currency in {q.currency for q in quotes.values()} - {wallet.currency}:
            try:
                rate = rate_of(currency)
            except FxRatesUnavailableError as error:
                raise FxRateUnavailableError(f"could not fetch the {currency}→{wallet.currency} rate right now; try again later") from error
            if rate is None:
                raise FxRateUnavailableError(f"no {currency}→{wallet.currency} rate{when}")
            rates[currency] = rate
        return value_wallet(wallet, quotes, rates)


def _end_of(day: date) -> datetime:
    """The first moment after `day`, in UTC: operations before it happened on or before that day."""
    return datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
