"""Request and response bodies of the HTTP API."""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Dividend, Operation, OperationType, PriceSource, Sell, Split, Withdrawal
from shadowfolio.domain.valuation import DailyValue, WalletValuation
from shadowfolio.domain.wallet import Wallet


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class UpdateWalletRequest(BaseModel):
    """Only the fields given change."""

    name: str | None = None
    withholding_rate: Decimal | None = None  # share of each dividend withheld as tax, e.g. 0.15 for 15%


class CopyWalletRequest(BaseModel):
    name: str


class CashMovementRequest(BaseModel):
    """A deposit or a withdrawal."""

    amount: Decimal
    timestamp: AwareDatetime | None = None  # defaults to now


class TradeRequest(BaseModel):
    symbol: str
    quantity: Decimal
    timestamp: AwareDatetime
    # The price the broker reported, with its currency. Leave both out to price the trade from market data
    # at `timestamp`; the trade is then marked as priced with hindsight.
    price: Decimal | None = None
    price_currency: Currency | None = None
    # Cash that left (buy) or entered (sell) the wallet before fees, in the wallet's currency, as the broker
    # reports it. Required when price_currency differs from the wallet's currency; computed for market prices.
    settled_amount: Decimal | None = None
    fees: Decimal = Decimal(0)


# Replacing an operation: the same fields as recording one, plus its type, which may change.
class DepositEdit(CashMovementRequest):
    type: Literal[OperationType.DEPOSIT]


class WithdrawalEdit(CashMovementRequest):
    type: Literal[OperationType.WITHDRAWAL]


class BuyEdit(TradeRequest):
    type: Literal[OperationType.BUY]


class SellEdit(TradeRequest):
    type: Literal[OperationType.SELL]


OperationEditRequest = Annotated[DepositEdit | WithdrawalEdit | BuyEdit | SellEdit, Field(discriminator="type")]


# Costs and gains are exact in the domain and rounded here, for display: money to cents, percentages to hundredths.
CENT = Decimal("0.01")


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _percent(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * 100).quantize(CENT, rounding=ROUND_HALF_EVEN)


def _ratio_percent(ratio: Decimal | None) -> Decimal | None:
    return None if ratio is None else (ratio * 100).quantize(CENT, rounding=ROUND_HALF_EVEN)


def _optional_cents(amount: Decimal | None) -> Decimal | None:
    return None if amount is None else _cents(amount)


def _checked_through(wallet: Wallet) -> date | None:
    held = wallet.holdings
    periods = [wallet.checked.get(symbol) for symbol in held]
    if not held or any(period is None for period in periods):
        return None
    return min(period.end for period in periods if period is not None)


class UncreditedDividendResponse(BaseModel):
    symbol: str
    ex_date: date
    per_share: Decimal
    currency: Currency


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    withholding_rate: Decimal  # share of each dividend withheld as tax, e.g. 0.15 for 15%
    cash: Decimal
    holdings: dict[str, Decimal]
    cost_basis: dict[str, Decimal]  # what each holding cost, in the wallet's currency (FIFO, fees included)
    realized_gain: Decimal  # from all sells so far, in the wallet's currency
    hindsight: bool  # some trade was priced from market data after the fact, so results are not a forward test
    # Corporate actions of the held symbols are applied up to this day (the earliest across them); null when nothing
    # is held, or when a held symbol has never been checked.
    splits_checked_through: date | None
    # Dividends the wallet qualified for but that were not credited: the data provider has no payment date for them.
    uncredited_dividends: list[UncreditedDividendResponse]

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        ledger = wallet.ledger
        return cls(
            id=wallet.id,
            name=wallet.name,
            currency=wallet.currency,
            withholding_rate=wallet.withholding_rate,
            cash=wallet.cash,
            holdings=wallet.holdings,
            cost_basis={symbol: _cents(position.cost) for symbol, position in ledger.positions.items()},
            realized_gain=_cents(ledger.realized_gain),
            hindsight=wallet.hindsight,
            splits_checked_through=_checked_through(wallet),
            uncredited_dividends=[
                UncreditedDividendResponse(symbol=e.symbol, ex_date=e.ex_date, per_share=e.per_share, currency=e.currency)
                for e in wallet.uncredited_dividends
            ],
        )


class OperationResponse(BaseModel):
    id: UUID
    type: OperationType
    timestamp: AwareDatetime
    amount: Decimal
    fees: Decimal
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    price_currency: Currency | None = None
    price_source: PriceSource | None = None  # trades only: entered (from the broker) or market (filled from market data)
    # Splits only: old_rate shares became new_rate shares (e.g. 1 → 10).
    split_old_rate: Decimal | None = None
    split_new_rate: Decimal | None = None
    automatic: bool = False  # added by the system from market data; cannot be edited or deleted
    had_effect: bool = True  # false for a split when no shares of its symbol were held then
    fx_rate: Decimal | None = None  # dividends only: the rate into the wallet's currency on the payment date
    # Dividends only, in the wallet's currency: before tax, and the tax withheld (amount is what was credited).
    gross: Decimal | None = None
    withholding: Decimal | None = None

    @classmethod
    def from_operation(cls, operation: Operation, had_effect: bool = True) -> "OperationResponse":
        match operation:
            case Deposit() | Withdrawal():
                return cls(id=operation.id, type=operation.type, timestamp=operation.timestamp, amount=operation.amount, fees=Decimal(0))
            case Buy() | Sell():
                trade = operation.trade
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.settled_amount,
                    fees=operation.fees,
                    symbol=trade.symbol,
                    quantity=trade.quantity,
                    price=trade.price,
                    price_currency=trade.price_currency,
                    price_source=trade.price_source,
                )
            case Split():
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=Decimal(0),
                    fees=Decimal(0),
                    symbol=operation.symbol,
                    split_old_rate=operation.old_rate,
                    split_new_rate=operation.new_rate,
                    automatic=True,
                    had_effect=had_effect,
                )
            case Dividend():
                # quantity: the shares that qualified; price: the amount per share, in its currency; amount: credited (net).
                return cls(
                    id=operation.id,
                    type=operation.type,
                    timestamp=operation.timestamp,
                    amount=operation.amount,
                    fees=Decimal(0),
                    symbol=operation.symbol,
                    quantity=operation.shares,
                    price=operation.per_share,
                    price_currency=operation.currency,
                    fx_rate=operation.fx_rate,
                    gross=operation.gross,
                    withholding=operation.withholding,
                    automatic=True,
                )


class FxRateResponse(BaseModel):
    rate: Decimal  # units of the wallet's currency per unit of the price's currency
    as_of: date


class HoldingValueResponse(BaseModel):
    symbol: str
    quantity: Decimal
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    value: Decimal  # in the price's currency
    fx_rate: FxRateResponse | None  # null when the price is already in the wallet's currency
    value_in_wallet_currency: Decimal
    cost: Decimal  # in the wallet's currency
    gain: Decimal  # unrealized, in the wallet's currency; negative for a loss
    gain_percent: Decimal  # of the cost
    previous_close: Decimal | None  # in the price's currency
    day_change: Decimal | None  # since the previous close, in the wallet's currency (price only, not exchange rates)
    day_change_percent: Decimal | None  # the price's move since the previous close


class ValuationResponse(BaseModel):
    currency: Currency
    cash: Decimal
    holdings: list[HoldingValueResponse]
    cost: Decimal  # of all holdings, in the wallet's currency
    gain: Decimal  # unrealized gain of all holdings
    gain_percent: Decimal | None  # of the cost; null when nothing is held
    day_change: Decimal | None  # of all holdings since the previous close; null if any holding has no previous close
    day_change_percent: Decimal | None  # of the holdings' value at the previous close
    total: Decimal  # cash plus holdings, in the wallet's currency

    @classmethod
    def from_valuation(cls, valuation: WalletValuation) -> "ValuationResponse":
        return cls(
            currency=valuation.currency,
            cash=valuation.cash,
            holdings=[
                HoldingValueResponse(
                    symbol=h.symbol,
                    quantity=h.quantity,
                    price=h.quote.price,
                    currency=h.quote.currency,
                    as_of=h.quote.as_of,
                    value=h.value,
                    fx_rate=FxRateResponse(rate=h.fx_rate.rate, as_of=h.fx_rate.as_of) if h.fx_rate else None,
                    value_in_wallet_currency=h.value_in_wallet_currency,
                    cost=_cents(h.cost),
                    gain=_cents(h.gain),
                    gain_percent=_percent(h.gain, h.cost),
                    previous_close=h.quote.previous_close,
                    day_change=_optional_cents(h.day_change),
                    day_change_percent=_ratio_percent(h.day_change_ratio),
                )
                for h in valuation.holdings
            ],
            cost=_cents(valuation.cost),
            gain=_cents(valuation.gain),
            gain_percent=_percent(valuation.gain, valuation.cost) if valuation.cost else None,
            day_change=_optional_cents(valuation.day_change),
            day_change_percent=_ratio_percent(valuation.day_change_ratio),
            total=valuation.total,
        )


class DailyValueResponse(BaseModel):
    """The wallet at the end of a day, valued at that day's closing prices, in its currency."""

    day: date
    cash: Decimal
    holdings_value: Decimal
    total: Decimal  # cash plus holdings
    net_deposits: Decimal  # deposits minus withdrawals up to then, so a chart can tell money put in from gains

    @classmethod
    def from_daily_value(cls, value: DailyValue) -> "DailyValueResponse":
        holdings_value = _cents(value.valuation.total - value.valuation.cash)
        cash = value.valuation.cash
        return cls(day=value.day, cash=cash, holdings_value=holdings_value, total=cash + holdings_value, net_deposits=value.net_deposits)


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    previous_close: Decimal | None


class SyncSummaryResponse(BaseModel):
    wallets: int  # wallets checked
    added: int
