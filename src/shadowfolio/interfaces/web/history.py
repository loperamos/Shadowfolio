"""Routes for recording what happened in a wallet."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import (
    AmountRequest,
    DepositRequest,
    TradeRequest,
    WalletResponse,
)
from shadowfolio.usecases.history import History


def history_router(history: History) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets/{wallet_id}/deposits")
    def deposit(wallet_id: UUID, request: DepositRequest) -> WalletResponse:
        try:
            wallet = history.deposit(wallet_id, request.amount, request.timestamp)
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/withdrawals")
    def withdraw(wallet_id: UUID, request: AmountRequest) -> WalletResponse:
        try:
            wallet = history.withdraw(wallet_id, request.amount)
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/buys")
    def record_buy(wallet_id: UUID, request: TradeRequest) -> WalletResponse:
        try:
            wallet = history.record_buy(
                wallet_id,
                request.to_trade(),
                request.timestamp,
                request.settled_amount,
                request.fees,
            )
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    @router.post("/wallets/{wallet_id}/sells")
    def record_sell(wallet_id: UUID, request: TradeRequest) -> WalletResponse:
        try:
            wallet = history.record_sell(
                wallet_id,
                request.to_trade(),
                request.timestamp,
                request.settled_amount,
                request.fees,
            )
        except DomainError as error:
            raise rule_violation(error) from error
        if wallet is None:
            raise wallet_not_found()
        return WalletResponse.from_wallet(wallet)

    return router
