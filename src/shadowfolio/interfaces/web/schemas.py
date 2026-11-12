"""Request and response bodies of the HTTP API."""

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


class AmountRequest(BaseModel):
    amount: Decimal


class DepositRequest(BaseModel):
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


class HoldingValueResponse(BaseModel):
    symbol: str
    quantity: Decimal
    price: Decimal
    currency: Currency
    as_of: AwareDatetime
    value: Decimal


class ValuationResponse(BaseModel):
    holdings: list[HoldingValueResponse]
    # Cash plus holdings, summed per currency; different currencies are not converted yet.
    totals: dict[Currency, Decimal]

    @classmethod
    def from_valuation(cls, valuation: WalletValuation) -> "ValuationResponse":
        return cls(
            holdings=[
                HoldingValueResponse(
                    symbol=h.symbol, quantity=h.quantity, price=h.quote.price, currency=h.quote.currency, as_of=h.quote.as_of, value=h.value
                )
                for h in valuation.holdings
            ],
            totals=valuation.totals,
        )
