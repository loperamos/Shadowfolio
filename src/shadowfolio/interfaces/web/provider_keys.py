"""Routes for the signed-in user's own market-data keys: save (or replace), list and remove."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request, Response

from shadowfolio.domain.errors import DomainError
from shadowfolio.domain.provider_keys import DataProvider
from shadowfolio.interfaces.web.errors import INVALID, NOT_FOUND, provider_key_not_found, rule_violation
from shadowfolio.interfaces.web.schemas import ProviderKeyResponse, SaveProviderKeyRequest
from shadowfolio.usecases.provider_keys import ProviderKeys

NO_CONTENT = 204


def provider_keys_router(provider_keys: ProviderKeys, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.get("/provider-keys")
    def list_provider_keys(user_id: str = Depends(current_user)) -> list[ProviderKeyResponse]:
        """The user's saved keys, by a hint: never their secrets."""
        return [ProviderKeyResponse.from_key(key) for key in provider_keys.list(user_id)]

    @router.put("/provider-keys/{provider}", responses=INVALID)
    def save_provider_key(
        provider: DataProvider, request: SaveProviderKeyRequest, user_id: str = Depends(current_user)
    ) -> ProviderKeyResponse:
        """Save the user's key for a provider, replacing any earlier one. Kept encrypted."""
        try:
            key = provider_keys.save(user_id, provider, request.key_id, request.secret)
        except DomainError as error:
            raise rule_violation(error) from error
        return ProviderKeyResponse.from_key(key)

    @router.delete("/provider-keys/{provider}", status_code=NO_CONTENT, responses=NOT_FOUND)
    def delete_provider_key(provider: DataProvider, user_id: str = Depends(current_user)) -> Response:
        """Forget the user's key for a provider."""
        if not provider_keys.delete(user_id, provider):
            raise provider_key_not_found()
        return Response(status_code=NO_CONTENT)

    return router
