"""Usage figures: how much each user uses Shadowfolio and, through it, each market-data provider (with their own key,
or the server's), counted per day. For admins, to see what the service costs its users' keys and itself."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Counter(StrEnum):
    REQUESTS = "requests"  # to Shadowfolio, from the web app or an agent
    CALLS = "calls"  # to a provider
    ERRORS = "errors"  # calls to a provider refused (an error status) or never answered
    CACHE_HITS = "cache_hits"  # price lookups answered from the cache
    CACHE_MISSES = "cache_misses"  # price lookups that had to ask the provider


# Where requests to Shadowfolio come from; calls to a provider are counted under its name (e.g. "alpaca").
WEB, MCP = "web", "mcp"
# Who calls made with the server's own keys (admins without keys of their own) are counted under.
SERVER_KEYS = "server keys"

# Records `n` of a counter, for the user and source it was made for.
RecordUsage = Callable[[Counter, int], None]


@dataclass(frozen=True)
class UsageKey:
    day: date  # in UTC
    user_id: str  # or SERVER_KEYS
    source: str  # WEB, MCP or a provider's name
    counter: Counter


@dataclass(frozen=True)
class UsageCount:
    key: UsageKey
    count: int
