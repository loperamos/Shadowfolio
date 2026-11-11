"""WalletRepository backed by a SQLite file."""

import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from shadowfolio.domain.wallet import Currency, Wallet

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL,
    cash TEXT NOT NULL
)
"""


class SqliteWalletRepository:
    def __init__(self, path: Path) -> None:
        self._path = path
        with closing(self._connect()) as conn, conn:
            conn.execute(_SCHEMA)

    def add(self, wallet: Wallet) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO wallets (id, owner_id, name, currency, cash) VALUES (?, ?, ?, ?, ?)",
                (
                    str(wallet.id),
                    wallet.owner_id,
                    wallet.name,
                    wallet.currency.value,
                    str(wallet.cash),
                ),
            )

    def get(self, wallet_id: UUID) -> Wallet | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, owner_id, name, currency, cash FROM wallets WHERE id = ?",
                (str(wallet_id),),
            ).fetchone()
        if row is None:
            return None
        return Wallet(
            id=UUID(row[0]),
            owner_id=row[1],
            name=row[2],
            currency=Currency(row[3]),
            cash=Decimal(row[4]),
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)
