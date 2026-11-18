"""Users and their plans: a user's tier sets the limits the use cases check, refused with the reason.

A plan's limits are the service's, per user, to keep it within what it can serve; a wallet's rules (see domain.rules)
are the owner's, per wallet. Signing in for the first time makes the account, on the free plan.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from shadowfolio.domain.errors import PlanLimitError, RateLimitError


class Tier(StrEnum):
    ADMIN = "admin"  # runs the service: no limits, and sets other users' tiers
    MEMBER = "member"  # trusted users, with more room
    FREE = "free"  # everyone who signs up


@dataclass(frozen=True)
class Limits:
    """What a plan allows; None for no limit."""

    wallets: int | None  # the most wallets a user may have at once
    orders_per_day: int | None  # orders placed in a day (UTC) across their wallets, by them or their agents
    access_tokens: int | None  # agent tokens at once, not counting revoked ones
    requests_per_minute: int | None  # to the web API and the MCP server together
    imports_per_day: int | None  # broker statements imported (saved, not previewed) in a day (UTC)


NO_LIMITS = Limits(wallets=None, orders_per_day=None, access_tokens=None, requests_per_minute=None, imports_per_day=None)
TIER_LIMITS: Mapping[Tier, Limits] = MappingProxyType(
    {
        Tier.ADMIN: NO_LIMITS,
        Tier.MEMBER: Limits(wallets=10, orders_per_day=100, access_tokens=10, requests_per_minute=600, imports_per_day=20),
        Tier.FREE: Limits(wallets=3, orders_per_day=20, access_tokens=2, requests_per_minute=120, imports_per_day=5),
    }
)


@dataclass(frozen=True)
class User:
    id: str  # the sign-in provider's, e.g. "google-oauth2|1005…"
    tier: Tier
    created_at: datetime  # when they first signed in

    @property
    def limits(self) -> Limits:
        return TIER_LIMITS[self.tier]

    @property
    def uses_server_keys(self) -> bool:
        """Whether market data may be fetched with the server's own keys when they have saved none: only admins, as
        what a development plan's key fetches may not be shown to other users."""
        return self.tier is Tier.ADMIN

    def with_tier(self, tier: Tier) -> "User":
        return replace(self, tier=tier)

    def check_new_wallet(self, owned: int) -> None:
        """Raise PlanLimitError if the user, owning `owned` wallets, may not make another."""
        allowed = self.limits.wallets
        if allowed is not None and owned >= allowed:
            raise PlanLimitError(f"your plan allows {allowed} wallets; delete one to make another")

    def check_new_order(self, placed_today: int) -> None:
        """Raise PlanLimitError if the user, having placed `placed_today` orders today (UTC), may not place another."""
        allowed = self.limits.orders_per_day
        if allowed is not None and placed_today >= allowed:
            raise PlanLimitError(f"your plan allows {allowed} orders a day; place more tomorrow (UTC)")

    def check_new_token(self, active: int) -> None:
        """Raise PlanLimitError if the user, with `active` agent tokens, may not make another."""
        allowed = self.limits.access_tokens
        if allowed is not None and active >= allowed:
            raise PlanLimitError(f"your plan allows {allowed} agent tokens at once; revoke one to make another")

    def check_new_import(self, imported_today: int) -> None:
        """Raise PlanLimitError if the user, having imported `imported_today` statements today (UTC), may not import
        another."""
        allowed = self.limits.imports_per_day
        if allowed is not None and imported_today >= allowed:
            raise PlanLimitError(f"your plan allows {allowed} imports a day; import more tomorrow (UTC)")

    def check_request(self, made: int, window_ends: datetime, now: datetime) -> None:
        """Raise RateLimitError if the user, having made `made` requests in the window ending at `window_ends`, may
        not make another now."""
        allowed = self.limits.requests_per_minute
        if allowed is not None and made >= allowed:
            wait = max(1, math.ceil((window_ends - now).total_seconds()))
            raise RateLimitError(f"your plan allows {allowed} requests a minute; try again in {wait} seconds", wait)
