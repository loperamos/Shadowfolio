"""News about listed companies."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Article:
    headline: str
    summary: str  # a line or two; may be empty
    source: str  # who published it, e.g. "benzinga"
    url: str  # where to read it
    published_at: datetime
