"""Возврат прогона на ЖИВОМ Postgres — там, где транзакции настоящие.

Hermetic-тесты гоняют InMemoryRepo. Двойник может согласиться с нами, а БД — нет: гонки,
порядок блокировок и идемпотентность через WHERE существуют только здесь.

Skipped unless TEST_DATABASE_URL is set (integration test).
"""
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
        await con.execute(
            "DROP TABLE IF EXISTS payments, billing, adrs, messages, artifacts, sessions, "
            "schema_migrations CASCADE"
        )
    await apply_migrations(pool)
    return pool


async def test_refund_roundtrip_on_live_db():
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        await repo.start_session_with_entitlement(1, "idea", "lite", free_runs=1)
        assert (await repo.get_billing(1))["free_used"] == 1

        assert await repo.abandon_session(1) is True
        assert (await repo.get_billing(1))["free_used"] == 0

        # прогон вернулся -> новый старт возможен, это не пейволл
        assert await repo.start_session_with_entitlement(1, "idea2", "lite", free_runs=1) is not None
    finally:
        await pool.close()


async def test_concurrent_double_reset_refunds_once():
    """Идемпотентность держит БД (WHERE status='active'), а не проверка в коде.

    Урок knowledge-base/lessons/pending-invoice-uniqueness.md: две конкурентные транзакции
    обе видят «можно» и обе делают. Здесь второй UPDATE обязан получить rowcount=0.
    """
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        await repo.start_session_with_entitlement(1, "idea", "lite", free_runs=1)

        results = await asyncio.gather(repo.abandon_session(1), repo.abandon_session(1))

        assert sorted(results) == [False, True], f"ровно один возврат, получили {results}"
        assert (await repo.get_billing(1))["free_used"] == 0, "не ниже нуля, не два прогона"
    finally:
        await pool.close()


async def test_concurrent_start_and_reset_do_not_deadlock():
    """Порядок блокировок billing->sessions одинаков в обоих методах.

    Обратный порядок (был в плане v1) = ABBA: /start и /reset одновременно → deadlock_detected
    → asyncpg бросает → человек видит «Упс».
    """
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        await repo.start_session_with_entitlement(1, "idea", "lite", free_runs=1)

        # гоняем вперемешку: любой дедлок всплывёт исключением
        for _ in range(10):
            await asyncio.gather(
                repo.abandon_session(1),
                repo.start_session_with_entitlement(1, "idea", "lite", free_runs=99),
                repo.abandon_session(1),
            )
    finally:
        await pool.close()


async def test_finish_cannot_resurrect_an_abandoned_session():
    """C1 на живой БД: условный UPDATE — единственное, что стоит между нами и бесплатной спекой."""
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        s = await repo.start_session_with_entitlement(1, "idea", "lite", free_runs=1)
        await repo.abandon_session(1)

        assert await repo.set_status_if_active(s.id, "finished") is False
        assert (await repo.get_billing(1))["free_used"] == 0, "прогон остаётся возвращённым"
    finally:
        await pool.close()


async def test_transcript_survives_reset():
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        s = await repo.start_session_with_entitlement(1, "idea", "lite", free_runs=1)
        await repo.add_message(s.id, "user", "моя идея")

        await repo.abandon_session(1)

        assert len(await repo.get_messages(s.id, 40)) == 1, "строку сессии не удаляем — она реестр"
    finally:
        await pool.close()


async def test_paid_run_refunded_as_paid():
    from launch11bot.db.pg_repo import PgRepo
    pool = await _fresh_pool()
    try:
        repo = PgRepo(pool)
        s = await repo.start_session_with_entitlement(1, "a", "lite", free_runs=1)  # free
        await repo.set_status(s.id, "finished")
        await repo.grant_paid_credit("ch1", 1, 100)
        await repo.start_session_with_entitlement(1, "b", "lite", free_runs=1)      # paid
        assert (await repo.get_billing(1))["paid_credits"] == 0

        await repo.abandon_session(1)

        b = await repo.get_billing(1)
        assert b["paid_credits"] == 1 and b["free_used"] == 1
    finally:
        await pool.close()
