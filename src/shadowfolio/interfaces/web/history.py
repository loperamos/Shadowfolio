"""Routes for recording, correcting and removing what happened in a wallet."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError, OperationNotFoundError
from shadowfolio.domain.money import Currency
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, operation_not_found, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import (
    BuyEdit,
    CashMovementRequest,
    DepositEdit,
    OperationEditRequest,
    SellEdit,
    TradeRequest,
    WalletResponse,
    WithdrawalEdit,
)
from shadowfolio.usecases.history import History


def history_router(history: History) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets/{wallet_id}/deposits", responses=NOT_FOUND | INVALID)
    def deposit(wallet_id: UUID, request: CashMovementRequest) -> WalletResponse:
        try:
            wallet = history.deposit(wallet_id, request.amount, request.timestamp)
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/withdrawals", responses=NOT_FOUND | INVALID)
    def withdraw(wallet_id: UUID, request: CashMovementRequest) -> WalletResponse:
        try:
            wallet = history.withdraw(wallet_id, request.amount, request.timestamp)
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/buys", responses=NOT_FOUND | INVALID)
    def record_buy(wallet_id: UUID, request: TradeRequest) -> WalletResponse:
        try:
            wallet = history.record_buy(wallet_id, *_trade_args(request))
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/sells", responses=NOT_FOUND | INVALID)
    def record_sell(wallet_id: UUID, request: TradeRequest) -> WalletResponse:
        try:
            wallet = history.record_sell(wallet_id, *_trade_args(request))
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.put("/wallets/{wallet_id}/operations/{operation_id}", responses=NOT_FOUND | INVALID)
    def edit_operation(wallet_id: UUID, operation_id: UUID, request: OperationEditRequest) -> WalletResponse:
        try:
            match request:
                case DepositEdit():
                    wallet = history.deposit(wallet_id, request.amount, request.timestamp, replacing=operation_id)
                case WithdrawalEdit():
                    wallet = history.withdraw(wallet_id, request.amount, request.timestamp, replacing=operation_id)
                case BuyEdit():
                    wallet = history.record_buy(wallet_id, *_trade_args(request), replacing=operation_id)
                case SellEdit():
                    wallet = history.record_sell(wallet_id, *_trade_args(request), replacing=operation_id)
        except OperationNotFoundError as error:
            raise operation_not_found() from error
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.delete("/wallets/{wallet_id}/operations/{operation_id}", responses=NOT_FOUND | INVALID)
    def delete_operation(wallet_id: UUID, operation_id: UUID) -> WalletResponse:
        try:
            wallet = history.delete_operation(wallet_id, operation_id)
        except OperationNotFoundError as error:
            raise operation_not_found() from error
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    return router


def _trade_args(request: TradeRequest) -> tuple[str, Decimal, datetime, Decimal | None, Currency | None, Decimal | None, Decimal]:
    """A trade request's fields, in the order the history use cases take them."""
    return (
        request.symbol,
        request.quantity,
        request.timestamp,
        request.price,
        request.price_currency,
        request.settled_amount,
        request.fees,
    )
