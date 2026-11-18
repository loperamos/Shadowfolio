"""ProviderKeyRepository in a SQLite file (the wallets' database, in a table of its own), each key encrypted with a
master key (Fernet: AES with an authentication code). The master key is kept apart from the database, so a copy of the
database alone (e.g. a backup) does not give the keys away; without it, the keys cannot be read."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from shadowfolio.domain.provider_keys import DataProvider, ProviderKey
from shadowfolio.ports.provider_key_repository import ProviderKeyRepository

MASTER_KEY_SETTING = "SHADOWFOLIO_KEYS_SECRET"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_keys (
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    key_id TEXT,
    secret TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, provider)
);
"""
_COLUMNS = "owner_id, provider, key_id, secret, saved_at"


class KeysUnreadableError(Exception):
    """The stored keys cannot be decrypted: the master key is not the one they were saved with."""


class SqliteProviderKeyRepository(ProviderKeyRepository):
    def __init__(self, path: Path, master_key: str) -> None:
        """`master_key` is a Fernet key (e.g. from `Fernet.generate_key()`)."""
        try:
            self._fernet = Fernet(master_key)
        except ValueError as error:
            raise ValueError(f"{MASTER_KEY_SETTING} is not a valid key: make one as the README says") from error
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def save(self, key: ProviderKey) -> None:
        row = (
            key.owner_id,
            key.provider.value,
            None if key.key_id is None else self._encrypt(key.key_id),
            self._encrypt(key.secret),
            key.saved_at.isoformat(),
        )
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(f"INSERT OR REPLACE INTO provider_keys ({_COLUMNS}) VALUES (?, ?, ?, ?, ?)", row)

    def get(self, owner_id: str, provider: DataProvider) -> ProviderKey | None:
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM provider_keys WHERE owner_id = ? AND provider = ?",  # noqa: S608
                (owner_id, provider.value),
            ).fetchone()
        return None if row is None else self._key(row)

    def list_by_owner(self, owner_id: str) -> list[ProviderKey]:
        with closing(sqlite3.connect(self._path)) as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM provider_keys WHERE owner_id = ? ORDER BY provider", (owner_id,)).fetchall()  # noqa: S608
        return [self._key(row) for row in rows]

    def delete(self, owner_id: str, provider: DataProvider) -> bool:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            deleted = conn.execute("DELETE FROM provider_keys WHERE owner_id = ? AND provider = ?", (owner_id, provider.value)).rowcount
        return deleted > 0

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise KeysUnreadableError(f"the stored market-data keys cannot be read with this {MASTER_KEY_SETTING}") from error

    def _key(self, row: tuple[str, str, str | None, str, str]) -> ProviderKey:
        owner_id, provider, key_id, secret, saved_at = row
        return ProviderKey(
            owner_id,
            DataProvider(provider),
            None if key_id is None else self._decrypt(key_id),
            self._decrypt(secret),
            datetime.fromisoformat(saved_at),
        )
