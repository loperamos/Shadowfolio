"""Import records: what a broker statement says happened, before it becomes a wallet's operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportRecord:
    """One operation read from a broker statement. Its fields come with the kinds of operation the import learns."""
