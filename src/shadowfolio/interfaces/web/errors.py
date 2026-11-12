"""HTTP errors shared by the routers."""

from fastapi import HTTPException

from shadowfolio.domain.errors import DomainError


def wallet_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="wallet not found")


def rule_violation(error: DomainError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))
