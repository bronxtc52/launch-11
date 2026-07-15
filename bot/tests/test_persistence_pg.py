"""Criteria 8, 12 — persistence + atomic single-active-session on a live Postgres.

Skipped unless TEST_DATABASE_URL is set (integration test)."""
import asyncio
import os
import pytest

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


async def _fresh_pool():
    import asyncpg
    from launch11bot.db.pg_repo import apply_migrations
    pool = await asyncpg.create_pool(DSN)
    async with pool.acquire() as con:
        # clean slate — drop the migrations ledger too, else apply_migrations skips rebuild
        await con.execute(
            "DROP TABLE IF EXISTS messages, artifacts, sessions, schema_migrations CASCADE"
        )
    await apply_migrations(pool)
    return pool


async def test_progress_survives_reconnect():
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo1 = PgRepo(pool)
        s = await repo1.start_session(555, "idea", "lite")
        await repo1.save_artifact(s.id, "L1", "body")
        await repo1.advance_step(s.id, "L1", "L2")
        # simulate process restart: brand-new repo over a new pool, same DB
        pool2 = await __import__("asyncpg").create_pool(DSN)
        try:
            repo2 = PgRepo(pool2)
            again = await repo2.get_active_session(555)
            assert again is not None
            assert again.current_step == "L2"
            arts = await repo2.get_artifacts(again.id)
            assert arts["L1"] == "body"
        finally:
            await pool2.close()
    finally:
        await pool.close()


async def test_concurrent_start_yields_single_active_session():
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        results = await asyncio.gather(
            *[repo.start_session(777, "idea", "lite") for _ in range(8)],
            return_exceptions=True,
        )
        sessions = [r for r in results if not isinstance(r, Exception)]
        assert sessions, "at least one start must succeed"
        ids = {s.id for s in sessions}
        assert len(ids) == 1, f"expected one active session, got {ids}"
    finally:
        await pool.close()
