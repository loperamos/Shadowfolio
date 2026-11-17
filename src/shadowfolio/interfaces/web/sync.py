"""Routes for keeping wallets up to date with corporate actions. Called by the daily job (or by hand)."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, rule_violation
from shadowfolio.interfaces.web.schemas import SyncSummaryResponse
from shadowfolio.usecases.sync import Sync


def sync_router(sync: Sync, job_check: Callable[[Request], None]) -> APIRouter:
    router = APIRouter()

    @router.post("/sync", responses=INVALID, dependencies=[Depends(job_check)])
    def sync_all_wallets() -> SyncSummaryResponse:
        try:
            summary = sync.all_wallets()
        except DomainError as error:
            raise rule_violation(error) from error
        return SyncSummaryResponse(wallets=summary.wallets, added=summary.added)

    return router
