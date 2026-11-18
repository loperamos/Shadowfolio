"""HTTP errors shared by the routers, and how they are documented in the API schema."""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from shadowfolio.domain.errors import DomainError


class FieldError(BaseModel):
    """One problem in a malformed request, as FastAPI reports it."""

    loc: list[str | int]
    msg: str
    type: str


class ErrorResponse(BaseModel):
    # A message for a missing resource or a broken business rule; a list of field errors when the request is malformed.
    detail: str | list[FieldError]


# Documented responses, attached to the routes that can return them.
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Not found"}}
FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"model": ErrorResponse, "description": "Only admins can do this"}}
INVALID: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse, "description": "Malformed request or broken business rule"}}


def wallet_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="wallet not found")


def operation_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="operation not found")


def order_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="order not found")


def token_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="access token not found")


def user_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="user not found")


def not_allowed(error: Exception) -> HTTPException:
    return HTTPException(status_code=403, detail=str(error))


def rule_violation(error: DomainError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))
