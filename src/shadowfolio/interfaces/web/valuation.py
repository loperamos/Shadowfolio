"""Routes for what a wallet is worth."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import ValuationResponse
from shadowfolio.usecases.valuation import Valuation


def valuation_router(valuation: Valuation) -> APIRouter:
    router = APIRouter()

    @router.get("/wallets/{wallet_id}/valuation", responses=NOT_FOUND | INVALID)
    def wallet_valuation(wallet_id: UUID, on: date | None = None) -> ValuationResponse:
        """What the wallet is worth now, or, given `on`, at the end of that day at its closing prices."""
        try:
            result = valuation.current(wallet_id) if on is None else valuation.on(wallet_id, on)
        except DomainError as error:
            raise rule_violation(error) from error
        if result is None:
            raise wallet_not_found()
        return ValuationResponse.from_valuation(result)

    return router
