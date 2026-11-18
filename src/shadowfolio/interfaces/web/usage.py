"""Routes for usage figures: admins only."""

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request

from shadowfolio.interfaces.web.errors import FORBIDDEN, not_allowed
from shadowfolio.interfaces.web.schemas import UsageCountResponse
from shadowfolio.usecases.usage import Usage
from shadowfolio.usecases.users import NotAllowedError


def usage_router(usage: Usage, current_user: Callable[[Request], str]) -> APIRouter:
    router = APIRouter()

    @router.get("/usage", responses=FORBIDDEN)
    def usage_figures(start: date | None = None, end: date | None = None, user_id: str = Depends(current_user)) -> list[UsageCountResponse]:
        """Per day (UTC), user and source: requests to Shadowfolio (web, mcp), calls to each provider and their errors,
        and price lookups answered from the cache or not; from `start` (default: a week before `end`) to `end`
        (default: today). Admins only."""
        try:
            counts = usage.report(user_id, start, end)
        except NotAllowedError as error:
            raise not_allowed(error) from error
        return [UsageCountResponse.from_count(count) for count in counts]

    return router
