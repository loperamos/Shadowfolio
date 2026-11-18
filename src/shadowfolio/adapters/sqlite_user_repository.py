"""UserRepository in a SQLite file: the wallets' database, in a table of its own."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from shadowfolio.domain.users import Tier, User
from shadowfolio.ports.user_repository import UserRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
_COLUMNS = "id, tier, created_at"


class SqliteUserRepository(UserRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(_SCHEMA)

    def add(self, user: User) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(f"INSERT INTO users ({_COLUMNS}) VALUES (?, ?, ?)", (user.id, user.tier.value, user.created_at.isoformat()))

    def update(self, user: User) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute("UPDATE users SET tier = ? WHERE id = ?", (user.tier.value, user.id))

    def get(self, user_id: str) -> User | None:
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()  # noqa: S608
        return None if row is None else _user(row)

    def list(self) -> list[User]:
        with closing(sqlite3.connect(self._path)) as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM users ORDER BY rowid").fetchall()  # noqa: S608
        return [_user(row) for row in rows]


def _user(row: tuple[str, str, str]) -> User:
    user_id, tier, created_at = row
    return User(user_id, Tier(tier), datetime.fromisoformat(created_at))
