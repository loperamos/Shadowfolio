"""Routes for the access tokens agents use with the MCP server: create, list and revoke."""

from uuid import UUID

from fastapi import APIRouter

from shadowfolio.domain.errors import DomainError
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, rule_violation, token_not_found
from shadowfolio.interfaces.web.schemas import AccessTokenResponse, CreateAccessTokenRequest, CreatedAccessTokenResponse
from shadowfolio.interfaces.web.wallets import LOCAL_OWNER
from shadowfolio.usecases.access_tokens import AccessTokens


def access_router(access_tokens: AccessTokens) -> APIRouter:
    router = APIRouter()

    @router.post("/access-tokens", status_code=201, responses=INVALID)
    def create_access_token(request: CreateAccessTokenRequest) -> CreatedAccessTokenResponse:
        """A new token for an agent, with its secret: shown only now, as only a hash of it is kept."""
        try:
            token, secret = access_tokens.create(LOCAL_OWNER, request.name, request.scope, request.wallet_ids)
        except DomainError as error:
            raise rule_violation(error) from error
        return CreatedAccessTokenResponse(token=AccessTokenResponse.from_token(token), secret=secret)

    @router.get("/access-tokens")
    def list_access_tokens() -> list[AccessTokenResponse]:
        """The tokens, revoked ones included, in the order they were created; never their secrets."""
        return [AccessTokenResponse.from_token(token) for token in access_tokens.list(LOCAL_OWNER)]

    @router.post("/access-tokens/{token_id}/revoke", responses=NOT_FOUND)
    def revoke_access_token(token_id: UUID) -> AccessTokenResponse:
        """Revoke a token: it stops working at once, and stays listed as revoked."""
        token = access_tokens.revoke(LOCAL_OWNER, token_id)
        if token is None:
            raise token_not_found()
        return AccessTokenResponse.from_token(token)

    return router
