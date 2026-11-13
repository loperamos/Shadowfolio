"""Routes for keeping wallets up to date with corporate actions. Called by the daily job (or by hand)."""

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, rule_violation
from shadowfolio.interfaces.web.schemas import SyncSummaryResponse
from shadowfolio.usecases.sync import Sync


def sync_router(sync: Sync) -> APIRouter:
    router = APIRouter()

    @router.post("/sync", responses=INVALID)
    def sync_all_wallets() -> SyncSummaryResponse:
        try:
            summary = sync.all_wallets()
        except DomainError as error:
            raise rule_violation(error) from error
        return SyncSummaryResponse(wallets=summary.wallets, added=summary.added)

    return router
