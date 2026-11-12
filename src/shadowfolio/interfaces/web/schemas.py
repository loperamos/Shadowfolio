"""Request and response bodies of the HTTP API."""

from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from shadowfolio.domain.wallet import Currency, Operation, OperationType, Trade, Wallet


class CreateWalletRequest(BaseModel):
    name: str
    currency: Currency
    cash: Decimal


class AmountRequest(BaseModel):
    amount: Decimal


class DepositRequest(BaseModel):
    amount: Decimal
    timestamp: AwareDatetime | None = None  # defaults to now


class BuyRequest(BaseModel):
    symbol: str
    quantity: Decimal
    price: Decimal
    price_currency: Currency
    timestamp: AwareDatetime
    # Cash that left the wallet before fees, in the wallet's currency, as the broker reports it.
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
        return cls(
            id=wallet.id,
            name=wallet.name,
            currency=wallet.currency,
            cash=wallet.cash,
            holdings=wallet.holdings,
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
        trade = operation.trade
        return cls(
            id=operation.id,
            type=operation.type,
            timestamp=operation.timestamp,
            amount=operation.amount,
            fees=operation.fees,
            symbol=trade.symbol if trade else None,
            quantity=trade.quantity if trade else None,
            price=trade.price if trade else None,
            price_currency=trade.price_currency if trade else None,
        )
