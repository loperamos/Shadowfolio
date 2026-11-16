"""AccessTokenRepository in a SQLite file: the wallets' database, in a table of its own."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import UUID

from shadowfolio.domain.access import AccessToken, Scope
from shadowfolio.ports.access_token_repository import AccessTokenRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_tokens (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    scope TEXT NOT NULL,
    wallet_ids TEXT NOT NULL,
    secret_hash TEXT NOT NULL UNIQUE,
    hint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);
"""
_COLUMNS = "id, owner_id, name, scope, wallet_ids, secret_hash, hint, created_at, last_used_at, revoked_at"
# The wallets a token may use are kept in one column, joined by this: ids never contain it.
WALLET_SEPARATOR = ","

Row = tuple[str, str, str, str, str, str, str, str, str | None, str | None]


class SqliteAccessTokenRepository(AccessTokenRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def add(self, token: AccessToken) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(f"INSERT INTO access_tokens ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _row(token))

    def update(self, token: AccessToken) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "UPDATE access_tokens SET name = ?, scope = ?, wallet_ids = ?, last_used_at = ?, revoked_at = ? WHERE id = ?",
                (token.name, token.scope.value, _wallets(token), _optional(token.last_used_at), _optional(token.revoked_at), str(token.id)),
            )

    def get(self, token_id: UUID) -> AccessToken | None:
        return self._one("id = ?", str(token_id))

    def find_by_hash(self, secret_hash: str) -> AccessToken | None:
        return self._one("secret_hash = ?", secret_hash)

    def list_by_owner(self, owner_id: str) -> list[AccessToken]:
        with closing(sqlite3.connect(self._path)) as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM access_tokens WHERE owner_id = ? ORDER BY rowid", (owner_id,)).fetchall()
        return [_token(row) for row in rows]

    def _one(self, condition: str, value: str) -> AccessToken | None:
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM access_tokens WHERE {condition}", (value,)).fetchone()  # noqa: S608
        return None if row is None else _token(row)


def _row(token: AccessToken) -> tuple[str, ...] | tuple[str | None, ...]:
    return (
        str(token.id),
        token.owner_id,
        token.name,
        token.scope.value,
        _wallets(token),
        token.secret_hash,
        token.hint,
        token.created_at.isoformat(),
        _optional(token.last_used_at),
        _optional(token.revoked_at),
    )


def _token(row: Row) -> AccessToken:
    token_id, owner_id, name, scope, wallet_ids, secret_hash, hint, created_at, last_used_at, revoked_at = row
    return AccessToken(
        id=UUID(token_id),
        owner_id=owner_id,
        name=name,
        scope=Scope(scope),
        wallet_ids=tuple(UUID(wallet_id) for wallet_id in wallet_ids.split(WALLET_SEPARATOR)),
        secret_hash=secret_hash,
        hint=hint,
        created_at=datetime.fromisoformat(created_at),
        last_used_at=None if last_used_at is None else datetime.fromisoformat(last_used_at),
        revoked_at=None if revoked_at is None else datetime.fromisoformat(revoked_at),
    )


def _wallets(token: AccessToken) -> str:
    return WALLET_SEPARATOR.join(str(wallet_id) for wallet_id in token.wallet_ids)


def _optional(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()
