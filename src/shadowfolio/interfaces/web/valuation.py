"""Routes for what a wallet is worth."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import ValuationResponse
from shadowfolio.usecases.valuation import Valuation


def valuation_router(valuation: Valuation) -> APIRouter:
    router = APIRouter()

    @router.get("/wallets/{wallet_id}/valuation")
    def current_valuation(wallet_id: UUID) -> ValuationResponse:
        try:
            result = valuation.current(wallet_id)
        except DomainError as error:
            raise rule_violation(error) from error
        if result is None:
            raise wallet_not_found()
        return ValuationResponse.from_valuation(result)

    return router
