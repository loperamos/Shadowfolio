"""Request and response bodies of the HTTP API."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

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


class WalletResponse(BaseModel):
    id: UUID
    name: str
    currency: Currency
    cash: Decimal
    holdings: dict[str, Decimal]

    @classmethod
    def from_wallet(cls, wallet: Wallet) -> "WalletResponse":
        return cls(id=wallet.id, name=wallet.name, currency=wallet.currency, cash=wallet.cash, holdings=wallet.holdings)


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


class ValuationResponse(BaseModel):
    currency: Currency
    cash: Decimal
    holdings: list[HoldingValueResponse]
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
                )
                for h in valuation.holdings
            ],
            total=valuation.total,
        )


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
