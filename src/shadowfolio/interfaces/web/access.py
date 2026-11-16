"""Routes for the access tokens agents use with the MCP server: create, list and revoke."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, token_not_found
from shadowfolio.interfaces.web.schemas import AccessTokenResponse, CreateAccessTokenRequest, CreatedAccessTokenResponse
from shadowfolio.usecases.access_tokens import AccessTokens


def access_router(access_tokens: AccessTokens, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.post("/access-tokens", status_code=201, responses=INVALID)
    def create_access_token(request: CreateAccessTokenRequest, user_id: str = Depends(current_user)) -> CreatedAccessTokenResponse:
        """A new token for an agent, with its secret: shown only now, as only a hash of it is kept."""
        try:
            token, secret = access_tokens.create(user_id, request.name, request.scope, request.wallet_ids)
        except DomainError as error:
            raise rule_violation(error) from error
        return CreatedAccessTokenResponse(token=AccessTokenResponse.from_token(token), secret=secret)

    @router.get("/access-tokens")
    def list_access_tokens(user_id: str = Depends(current_user)) -> list[AccessTokenResponse]:
        """The tokens, revoked ones included, in the order they were created; never their secrets."""
        return [AccessTokenResponse.from_token(token) for token in access_tokens.list(user_id)]

    @router.post("/access-tokens/{token_id}/revoke", responses=NOT_FOUND)
    def revoke_access_token(token_id: UUID, user_id: str = Depends(current_user)) -> AccessTokenResponse:
        """Revoke a token: it stops working at once, and stays listed as revoked."""
        token = access_tokens.revoke(user_id, token_id)
        if token is None:
            raise token_not_found()
        return AccessTokenResponse.from_token(token)

    return router
