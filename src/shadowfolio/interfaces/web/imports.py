"""Routes for importing a broker's statement into a wallet: a preview first, then the import."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, wallet_not_found
from shadowfolio.interfaces.web.schemas import ImportResponse, StatementRequest
from shadowfolio.usecases.imports import Imports


def imports_router(imports: Imports) -> APIRouter:
    router = APIRouter()

    @router.post("/wallets/{wallet_id}/imports/degiro/preview", responses=NOT_FOUND | INVALID)
    def preview_degiro_import(wallet_id: UUID, request: StatementRequest) -> ImportResponse:
        """What importing DEGIRO's Transactions and Account exports would do to the wallet. Saves nothing."""
        return _import(imports, wallet_id, request, save=False)

    @router.post("/wallets/{wallet_id}/imports/degiro", responses=NOT_FOUND | INVALID)
    def import_degiro(wallet_id: UUID, request: StatementRequest) -> ImportResponse:
        """Import DEGIRO's Transactions and Account exports into the wallet, if every record goes in."""
        return _import(imports, wallet_id, request, save=True)

    return router


def _import(imports: Imports, wallet_id: UUID, request: StatementRequest, save: bool) -> ImportResponse:
    try:
        report = imports.statement(wallet_id, request.transactions, request.account, save)
    except DomainError as error:
        raise rule_violation(error) from error
    if report is None:
        raise wallet_not_found()
    return ImportResponse.from_report(report)
