"""Postgres Repo (asyncpg). Atomic transitions + single-active-session invariant."""
from __future__ import annotations

from pathlib import Path

from ..pipeline import steps
from .repo import Session

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


async def apply_migrations(pool) -> None:
    async with pool.acquire() as con:
        await con.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r["name"] for r in await con.fetch("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            async with con.transaction():
                await con.execute(path.read_text())
                await con.execute("INSERT INTO schema_migrations (name) VALUES ($1)", path.name)


def _row_to_session(r) -> Session:
    return Session(r["id"], r["tg_user_id"], r["slug"], r["version"], r["current_step"], r["status"])


class PgRepo:
    def __init__(self, pool):
        self.pool = pool

    async def get_active_session(self, tg_user_id: int) -> Session | None:
        async with self.pool.acquire() as con:
            r = await con.fetchrow(
                "SELECT * FROM sessions WHERE tg_user_id=$1 AND status='active'", tg_user_id
            )
            return _row_to_session(r) if r else None

    async def start_session(self, tg_user_id: int, slug: str, version: str) -> Session:
        first = steps.first_step_id(version)
        async with self.pool.acquire() as con, con.transaction():
            r = await con.fetchrow(
                """
                INSERT INTO sessions (tg_user_id, slug, version, current_step, status)
                VALUES ($1, $2, $3, $4, 'active')
                ON CONFLICT (tg_user_id) WHERE status = 'active' DO NOTHING
                RETURNING *
                """,
                tg_user_id, slug, version, first,
            )
            if r is None:  # lost the race — an active session already exists
                r = await con.fetchrow(
                    "SELECT * FROM sessions WHERE tg_user_id=$1 AND status='active'", tg_user_id
                )
            return _row_to_session(r)

    async def save_artifact(self, session_id: int, step_id: str, markdown: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO artifacts (session_id, step_id, markdown) VALUES ($1, $2, $3)
                ON CONFLICT (session_id, step_id)
                DO UPDATE SET markdown = EXCLUDED.markdown, updated_at = now()
                """,
                session_id, step_id, markdown,
            )

    async def get_artifacts(self, session_id: int) -> dict[str, str]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT step_id, markdown FROM artifacts WHERE session_id=$1", session_id
            )
            return {r["step_id"]: r["markdown"] for r in rows}

    async def advance_step(self, session_id: int, from_step: str, to_step: str) -> bool:
        async with self.pool.acquire() as con:
            res = await con.execute(
                "UPDATE sessions SET current_step=$3, updated_at=now() "
                "WHERE id=$1 AND current_step=$2",
                session_id, from_step, to_step,
            )
            return res.endswith(" 1")  # "UPDATE 1" on success

    async def set_status(self, session_id: int, status: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET status=$2, updated_at=now() WHERE id=$1", session_id, status
            )

    async def add_message(self, session_id: int, role: str, text: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO messages (session_id, role, text) VALUES ($1, $2, $3)",
                session_id, role, text,
            )

    async def get_messages(self, session_id: int, limit: int) -> list[tuple[str, str]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT role, text FROM (SELECT role, text, created_at FROM messages "
                "WHERE session_id=$1 ORDER BY id DESC LIMIT $2) t ORDER BY created_at ASC",
                session_id, limit,
            )
            return [(r["role"], r["text"]) for r in rows]

    async def delete_session(self, tg_user_id: int) -> None:
        async with self.pool.acquire() as con:
            await con.execute("DELETE FROM sessions WHERE tg_user_id=$1", tg_user_id)
