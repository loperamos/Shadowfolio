"""Routes for the signed-in user's account, and for admins: listing users and setting their tiers."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request

from shadowfolio.interfaces.web.errors import FORBIDDEN, NOT_FOUND, not_allowed, user_not_found
from shadowfolio.interfaces.web.schemas import SetTierRequest, UserResponse
from shadowfolio.usecases.provider_keys import ProviderKeys
from shadowfolio.usecases.users import NotAllowedError, Users


def users_router(users: Users, provider_keys: ProviderKeys, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.get("/me")
    def get_me(user_id: str = Depends(current_user)) -> UserResponse:
        """The signed-in user: their tier, what their plan allows, and the market-data keys they still need to connect."""
        return UserResponse.from_user(users.user(user_id), provider_keys.missing(user_id))

    @router.get("/users", responses=FORBIDDEN)
    def list_users(user_id: str = Depends(current_user)) -> list[UserResponse]:
        """Every user, as they first signed in. Admins only."""
        try:
            return [UserResponse.from_user(user) for user in users.list(user_id)]
        except NotAllowedError as error:
            raise not_allowed(error) from error

    @router.put("/users/{target_id}/tier", responses=FORBIDDEN | NOT_FOUND)
    def set_user_tier(target_id: str, request: SetTierRequest, user_id: str = Depends(current_user)) -> UserResponse:
        """Put a user who has signed in on a tier. Admins only."""
        try:
            user = users.set_tier(user_id, target_id, request.tier)
        except NotAllowedError as error:
            raise not_allowed(error) from error
        if user is None:
            raise user_not_found()
        return UserResponse.from_user(user)

    return router
