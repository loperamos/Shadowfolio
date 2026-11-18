"""Users and their plans: a user's tier sets the limits the use cases check, refused with the reason.

A plan's limits are the service's, per user, to keep it within what it can serve; a wallet's rules (see domain.rules)
are the owner's, per wallet. Signing in for the first time makes the account, on the free plan.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from shadowfolio.domain.errors import PlanLimitError


class Tier(StrEnum):
    ADMIN = "admin"  # runs the service: no limits, and sets other users' tiers
    MEMBER = "member"  # trusted users, with more room
    FREE = "free"  # everyone who signs up


@dataclass(frozen=True)
class Limits:
    """What a plan allows; None for no limit."""

    wallets: int | None  # the most wallets a user may have at once


TIER_LIMITS: Mapping[Tier, Limits] = MappingProxyType(
    {Tier.ADMIN: Limits(wallets=None), Tier.MEMBER: Limits(wallets=10), Tier.FREE: Limits(wallets=3)}
)


@dataclass(frozen=True)
class User:
    id: str  # the sign-in provider's, e.g. "google-oauth2|1005…"
    tier: Tier
    created_at: datetime  # when they first signed in

    @property
    def limits(self) -> Limits:
        return TIER_LIMITS[self.tier]

    def with_tier(self, tier: Tier) -> "User":
        return replace(self, tier=tier)

    def check_new_wallet(self, owned: int) -> None:
        """Raise PlanLimitError if the user, owning `owned` wallets, may not make another."""
        allowed = self.limits.wallets
        if allowed is not None and owned >= allowed:
            raise PlanLimitError(f"your plan allows {allowed} wallets; delete one to make another")
