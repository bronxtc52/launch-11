"""Postgres Repo (asyncpg). Atomic transitions + single-active-session invariant."""
from __future__ import annotations

import json
from pathlib import Path

from ..pipeline import steps
from .repo import VERDICTS, Session

# Migrations ship as package data, so this resolves correctly both from the repo and
# from an installed wheel (site-packages) — a repo-relative path silently found zero
# files inside the container and left the schema uncreated.
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


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
    # every query uses SELECT * / RETURNING *, so the dialog-state columns are present
    return Session(r["id"], r["tg_user_id"], r["slug"], r["version"], r["current_step"],
                   r["status"], current_question=r["current_question"],
                   last_verdict=r["last_verdict"],
                   current_options=json.loads(r["current_options"]) if r.get("current_options") else None,
                   clarify_count=r["clarify_count"], clarify_budget=r["clarify_budget"])


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

    async def save_and_advance(self, session_id, step_id, markdown, from_step, to_step) -> bool:
        async with self.pool.acquire() as con, con.transaction():
            await con.execute(
                """
                INSERT INTO artifacts (session_id, step_id, markdown) VALUES ($1, $2, $3)
                ON CONFLICT (session_id, step_id)
                DO UPDATE SET markdown = EXCLUDED.markdown, updated_at = now()
                """,
                session_id, step_id, markdown,
            )
            res = await con.execute(
                "UPDATE sessions SET current_step=$3, updated_at=now() "
                "WHERE id=$1 AND current_step=$2",
                session_id, from_step, to_step,
            )
            return res.endswith(" 1")

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

    async def set_version(self, session_id: int, version: str, first_step: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET version=$2, current_step=$3, updated_at=now() WHERE id=$1",
                session_id, version, first_step,
            )

    async def create_adr(self, session_id: int, title: str, markdown: str) -> int:
        async with self.pool.acquire() as con, con.transaction():
            n = await con.fetchval(
                "SELECT COALESCE(MAX(n), 0) + 1 FROM adrs WHERE session_id=$1", session_id
            )
            await con.execute(
                "INSERT INTO adrs (session_id, n, title, markdown) VALUES ($1, $2, $3, $4)",
                session_id, n, title, markdown,
            )
            return n

    async def get_adrs(self, session_id: int) -> list[dict]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT n, title, markdown FROM adrs WHERE session_id=$1 ORDER BY n", session_id
            )
            return [{"n": r["n"], "title": r["title"], "markdown": r["markdown"]} for r in rows]

    async def start_session_with_entitlement(self, tg_user_id, slug, version, free_runs):
        first = steps.first_step_id(version)
        async with self.pool.acquire() as con, con.transaction():
            # ensure a billing row and lock it — serializes concurrent starts for this user
            await con.execute(
                "INSERT INTO billing (tg_user_id) VALUES ($1) ON CONFLICT DO NOTHING", tg_user_id)
            b = await con.fetchrow(
                "SELECT free_used, paid_credits FROM billing WHERE tg_user_id=$1 FOR UPDATE",
                tg_user_id)
            existing = await con.fetchrow(
                "SELECT * FROM sessions WHERE tg_user_id=$1 AND status='active'", tg_user_id)
            if existing:
                return _row_to_session(existing)  # resume — no consume
            if b["free_used"] < free_runs:
                await con.execute(
                    "UPDATE billing SET free_used=free_used+1, updated_at=now() WHERE tg_user_id=$1",
                    tg_user_id)
            elif b["paid_credits"] > 0:
                await con.execute(
                    "UPDATE billing SET paid_credits=paid_credits-1, updated_at=now() "
                    "WHERE tg_user_id=$1", tg_user_id)
            else:
                return None  # no entitlement — payment needed, no session created
            row = await con.fetchrow(
                "INSERT INTO sessions (tg_user_id, slug, version, current_step, status) "
                "VALUES ($1, $2, $3, $4, 'active') RETURNING *",
                tg_user_id, slug, version, first)
            return _row_to_session(row)

    async def grant_paid_credit(self, charge_id, tg_user_id, stars) -> bool:
        async with self.pool.acquire() as con, con.transaction():
            res = await con.execute(
                "INSERT INTO payments (charge_id, tg_user_id, stars) VALUES ($1, $2, $3) "
                "ON CONFLICT (charge_id) DO NOTHING",
                charge_id, tg_user_id, stars)
            if not res.endswith(" 1"):  # duplicate charge — no second credit
                return False
            await con.execute(
                "INSERT INTO billing (tg_user_id) VALUES ($1) ON CONFLICT DO NOTHING", tg_user_id)
            await con.execute(
                "UPDATE billing SET paid_credits=paid_credits+1, updated_at=now() WHERE tg_user_id=$1",
                tg_user_id)
            return True

    async def get_billing(self, tg_user_id) -> dict:
        async with self.pool.acquire() as con:
            r = await con.fetchrow(
                "SELECT free_used, paid_credits FROM billing WHERE tg_user_id=$1", tg_user_id)
            return ({"free_used": r["free_used"], "paid_credits": r["paid_credits"]} if r
                    else {"free_used": 0, "paid_credits": 0})

    async def set_question(self, session_id: int, question: str | None,
                           options: list[str] | None = None) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET current_question=$2, current_options=$3, updated_at=now() "
                "WHERE id=$1",
                session_id, question, json.dumps(options) if options else None)

    async def set_slug(self, session_id: int, slug: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET slug=$2, updated_at=now() WHERE id=$1", session_id, slug)

    async def set_clarify_count(self, session_id: int, n: int) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET clarify_count=$2, updated_at=now() WHERE id=$1", session_id, n)

    async def set_verdict(self, session_id: int, verdict: str | None) -> None:
        if verdict is not None and verdict not in VERDICTS:
            raise ValueError(f"bad verdict: {verdict}")
        async with self.pool.acquire() as con:
            await con.execute(
                "UPDATE sessions SET last_verdict=$2, updated_at=now() WHERE id=$1",
                session_id, verdict)

    async def add_message(self, session_id: int, role: str, text: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO messages (session_id, role, text) VALUES ($1, $2, $3)",
                session_id, role, text,
            )

    async def get_messages(self, session_id: int, limit: int) -> list[tuple[str, str]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT role, text FROM (SELECT id, role, text FROM messages "
                "WHERE session_id=$1 ORDER BY id DESC LIMIT $2) t ORDER BY id ASC",
                session_id, limit,
            )
            return [(r["role"], r["text"]) for r in rows]

    async def delete_session(self, tg_user_id: int) -> None:
        async with self.pool.acquire() as con:
            await con.execute("DELETE FROM sessions WHERE tg_user_id=$1", tg_user_id)
