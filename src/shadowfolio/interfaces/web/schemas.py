"""Request and response bodies of the HTTP API."""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from shadowfolio.domain.money import Currency
from shadowfolio.domain.operations import Buy, Deposit, Operation, OperationType, Sell, Trade, Withdrawal
from shadowfolio.domain.valuation import WalletValuation
from shadowfolio.domain.wallet import Wallet


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class RenameWalletRequest(BaseModel):
    name: str


class CopyWalletRequest(BaseModel):
    name: str


class CashMovementRequest(BaseModel):
    """A deposit or a withdrawal."""

    amount: Decimal
    timestamp: AwareDatetime | None = None  # defaults to now


class TradeRequest(BaseModel):
    symbol: str
    quantity: Decimal
    price: Decimal
    price_currency: Currency
    timestamp: AwareDatetime
    # Cash that left (buy) or entered (sell) the wallet before fees, in the wallet's currency,
    # as the broker reports it.
    # Required when price_currency differs from the wallet's currency.
    settled_amount: Decimal | None = None
    fees: Decimal = Decimal(0)

    def to_trade(self) -> Trade:
        return Trade(self.symbol, self.quantity, self.price, self.price_currency)


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


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    cash: Decimal
    holdings: dict[str, Decimal]
    cost_basis: dict[str, Decimal]  # what each holding cost, in the wallet's currency (FIFO, fees included)
    realized_gain: Decimal  # from all sells so far, in the wallet's currency

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        ledger = wallet.ledger
        return cls(
            id=wallet.id,
            name=wallet.name,
            currency=wallet.currency,
            cash=wallet.cash,
            holdings=wallet.holdings,
            cost_basis={symbol: _cents(position.cost) for symbol, position in ledger.positions.items()},
            realized_gain=_cents(ledger.realized_gain),
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

    @classmethod
    def from_operation(cls, operation: Operation) -> "OperationResponse":
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


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    previous_close: Decimal | None
