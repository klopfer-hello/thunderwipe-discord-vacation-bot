"""Database access layer for the guild vacation bot.

Abstracts over PostgreSQL (asyncpg) and SQLite (aiosqlite). The driver is
selected by the presence of DATABASE_URL:

    * DATABASE_URL set  -> PostgreSQL via asyncpg
    * DATABASE_URL empty -> SQLite via aiosqlite (file: vacations.db)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

SQLITE_PATH = "vacations.db"


@dataclass
class Vacation:
    id: int
    user_id: str
    username: str
    start_date: date
    end_date: date


def _is_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Cannot convert {type(value).__name__} to date")


class Database:
    """Async database wrapper. Call `connect()` once at startup, `close()` at shutdown."""

    def __init__(self) -> None:
        self._pg_pool = None  # asyncpg.Pool
        self._sqlite = None  # aiosqlite.Connection
        self._postgres = _is_postgres()

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        if self._postgres:
            import asyncpg

            self._pg_pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        else:
            import aiosqlite

            self._sqlite = await aiosqlite.connect(SQLITE_PATH)
            await self._sqlite.execute("PRAGMA foreign_keys = ON")
            await self._sqlite.commit()
        await self._create_schema()

    async def close(self) -> None:
        if self._pg_pool is not None:
            await self._pg_pool.close()
        if self._sqlite is not None:
            await self._sqlite.close()

    # ------------------------------------------------------------------ schema

    async def _create_schema(self) -> None:
        if self._postgres:
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS vacations (
                    id          SERIAL PRIMARY KEY,
                    user_id     TEXT        NOT NULL,
                    username    TEXT        NOT NULL,
                    start_date  DATE        NOT NULL,
                    end_date    DATE        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_vacations_dates ON vacations (start_date, end_date)",
                """
                CREATE TABLE IF NOT EXISTS bot_config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """,
            ]
            async with self._pg_pool.acquire() as conn:
                for s in stmts:
                    await conn.execute(s)
        else:
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS vacations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    username    TEXT NOT NULL,
                    start_date  TEXT NOT NULL,
                    end_date    TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_vacations_dates ON vacations (start_date, end_date)",
                """
                CREATE TABLE IF NOT EXISTS bot_config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """,
            ]
            for s in stmts:
                await self._sqlite.execute(s)
            await self._sqlite.commit()

    # ------------------------------------------------------------------ low-level helpers

    async def _fetch_all(self, pg_sql: str, sqlite_sql: str, *args: Any) -> list[dict]:
        if self._postgres:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(pg_sql, *args)
            return [dict(r) for r in rows]
        cur = await self._sqlite.execute(sqlite_sql, args)
        cols = [c[0] for c in cur.description] if cur.description else []
        rows = await cur.fetchall()
        await cur.close()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def _fetch_one(self, pg_sql: str, sqlite_sql: str, *args: Any) -> dict | None:
        rows = await self._fetch_all(pg_sql, sqlite_sql, *args)
        return rows[0] if rows else None

    async def _execute(self, pg_sql: str, sqlite_sql: str, *args: Any) -> None:
        if self._postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(pg_sql, *args)
            return
        await self._sqlite.execute(sqlite_sql, args)
        await self._sqlite.commit()

    # ------------------------------------------------------------------ vacation queries

    async def add_vacation(
        self, user_id: str, username: str, start: date, end: date
    ) -> int:
        """Insert a vacation; returns the new row id."""
        if self._postgres:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO vacations (user_id, username, start_date, end_date)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    user_id,
                    username,
                    start,
                    end,
                )
            return row["id"]
        cur = await self._sqlite.execute(
            """
            INSERT INTO vacations (user_id, username, start_date, end_date)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, start.isoformat(), end.isoformat()),
        )
        await self._sqlite.commit()
        new_id = cur.lastrowid
        await cur.close()
        return new_id

    async def delete_vacation(self, vacation_id: int, user_id: str) -> bool:
        """Delete a vacation only if it belongs to `user_id`. Returns True if a row was removed."""
        if self._postgres:
            async with self._pg_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM vacations WHERE id = $1 AND user_id = $2",
                    vacation_id,
                    user_id,
                )
            # result is e.g. "DELETE 1"
            return result.endswith(" 1")
        cur = await self._sqlite.execute(
            "DELETE FROM vacations WHERE id = ? AND user_id = ?",
            (vacation_id, user_id),
        )
        await self._sqlite.commit()
        deleted = cur.rowcount > 0
        await cur.close()
        return deleted

    async def get_upcoming_vacations_for_user(
        self, user_id: str, today: date | None = None
    ) -> list[Vacation]:
        today = today or date.today()
        rows = await self._fetch_all(
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE user_id = $1 AND end_date >= $2
            ORDER BY start_date ASC
            """,
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE user_id = ? AND end_date >= ?
            ORDER BY start_date ASC
            """,
            user_id,
            today if self._postgres else today.isoformat(),
        )
        return [self._row_to_vacation(r) for r in rows]

    async def get_vacations_overlapping_for_user(
        self, user_id: str, start: date, end: date
    ) -> list[Vacation]:
        rows = await self._fetch_all(
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE user_id = $1
              AND start_date <= $3
              AND end_date >= $2
            ORDER BY start_date ASC
            """,
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE user_id = ?
              AND start_date <= ?
              AND end_date >= ?
            ORDER BY start_date ASC
            """,
            *(
                (user_id, start, end)
                if self._postgres
                else (user_id, end.isoformat(), start.isoformat())
            ),
        )
        return [self._row_to_vacation(r) for r in rows]

    async def get_absent_on(self, target: date) -> list[Vacation]:
        rows = await self._fetch_all(
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE start_date <= $1 AND end_date >= $1
            ORDER BY username ASC
            """,
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE start_date <= ? AND end_date >= ?
            ORDER BY username ASC
            """,
            *(
                (target,)
                if self._postgres
                else (target.isoformat(), target.isoformat())
            ),
        )
        return [self._row_to_vacation(r) for r in rows]

    async def get_vacations_in_range(self, start: date, end: date) -> list[Vacation]:
        """All vacations that overlap [start, end]."""
        rows = await self._fetch_all(
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE start_date <= $2 AND end_date >= $1
            ORDER BY start_date ASC, username ASC
            """,
            """
            SELECT id, user_id, username, start_date, end_date
            FROM vacations
            WHERE start_date <= ? AND end_date >= ?
            ORDER BY start_date ASC, username ASC
            """,
            *((start, end) if self._postgres else (end.isoformat(), start.isoformat())),
        )
        return [self._row_to_vacation(r) for r in rows]

    async def get_absence_counts_for_range(
        self, start: date, end: date
    ) -> dict[date, int]:
        """Return {day: number_of_distinct_members_absent_that_day} for each day in [start, end]."""
        vacations = await self.get_vacations_in_range(start, end)
        # Use a set of user_ids per day to avoid double-counting overlapping entries from the same user.
        per_day: dict[date, set[str]] = {}
        day_count = (end - start).days + 1
        from datetime import timedelta

        for i in range(day_count):
            per_day[start + timedelta(days=i)] = set()
        for v in vacations:
            d = max(v.start_date, start)
            last = min(v.end_date, end)
            while d <= last:
                per_day.setdefault(d, set()).add(v.user_id)
                d = d.fromordinal(d.toordinal() + 1)
        return {d: len(users) for d, users in per_day.items()}

    # ------------------------------------------------------------------ config kv

    async def get_config(self, key: str) -> str | None:
        row = await self._fetch_one(
            "SELECT value FROM bot_config WHERE key = $1",
            "SELECT value FROM bot_config WHERE key = ?",
            key,
        )
        return row["value"] if row else None

    async def set_config(self, key: str, value: str) -> None:
        if self._postgres:
            await self._execute(
                """
                INSERT INTO bot_config (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                "",  # unused
                key,
                value,
            )
            return
        # SQLite path
        await self._sqlite.execute(
            """
            INSERT INTO bot_config (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self._sqlite.commit()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _row_to_vacation(row: dict) -> Vacation:
        return Vacation(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            start_date=_to_date(row["start_date"]),
            end_date=_to_date(row["end_date"]),
        )


# Module-level singleton so cogs can import a ready-to-use handle.
db = Database()


async def init_db() -> None:
    await db.connect()


async def close_db() -> None:
    await db.close()
