"""Право на прогон не должно сгорать за наш счёт.

Инцидент 2026-07-17: первый живой пользователь сжёг единственный бесплатный прогон на НАШЕМ
сбое (Anthropic 529 семь минут), нажал «начать заново» — delete_session удалил сессию без
возврата → пейволл. Он оплатил нашу поломку.

Модель: списываем на старте (атомарность оставлена), возвращаем, если spec.md не выдан.
Несущий инвариант: строку сессии НЕЛЬЗЯ удалять — она реестр списания.
"""
import pytest
from launch11bot.billing.service import BillingService, NEEDS_PAYMENT

OWNER = 424242


@pytest.fixture
def billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")


@pytest.fixture
def owner_billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон",
                          owners={OWNER})


# ── критерий 1: наш сбой не стоит человеку прогона ──────────────────────────────

async def test_reset_returns_the_free_run(billing, repo):
    """Ровно инцидент: прогон начат, ничего не выдано, человек начал заново."""
    await billing.start_session(1, slug="idea", version="lite")
    assert (await repo.get_billing(1))["free_used"] == 1

    refunded = await repo.abandon_session(1)

    assert refunded is True
    assert (await repo.get_billing(1))["free_used"] == 0, "прогон обязан вернуться"


async def test_after_reset_next_start_is_not_a_paywall(billing, repo):
    """То, обо что разбился живой человек: «начать заново» → плати 100⭐."""
    await billing.start_session(1, slug="idea", version="lite")
    await repo.abandon_session(1)

    result = await billing.start_session(1, slug="idea2", version="lite")

    assert result is not NEEDS_PAYMENT, "после возврата пейволла быть не должно"


# ── критерий 2: возврат идемпотентен (иначе бесконечные бесплатные прогоны) ──────

async def test_double_reset_refunds_once(billing, repo):
    await billing.start_session(1, slug="idea", version="lite")

    first = await repo.abandon_session(1)
    second = await repo.abandon_session(1)

    assert first is True and second is False
    assert (await repo.get_billing(1))["free_used"] == 0, "не ниже нуля, не второй прогон"


async def test_reset_without_session_is_a_noop(billing, repo):
    assert await repo.abandon_session(999) is False
    assert (await repo.get_billing(999))["free_used"] == 0


# ── критерий 3: ценность доставлена → возврата нет ──────────────────────────────

async def test_no_refund_after_the_spec_was_delivered(billing, repo):
    session = await billing.start_session(1, slug="idea", version="lite")
    await repo.set_status(session.id, "finished")

    refunded = await repo.abandon_session(1)

    assert refunded is False
    assert (await repo.get_billing(1))["free_used"] == 1, "spec.md выдан — прогон честно потрачен"


# ── критерий 4: транскрипт переживает reset (наша поверхность отладки) ──────────

async def test_reset_keeps_the_transcript(billing, repo):
    session = await billing.start_session(1, slug="idea", version="lite")
    await repo.add_message(session.id, "user", "моя идея")
    await repo.add_message(session.id, "assistant", "вопрос?")

    await repo.abandon_session(1)

    assert len(await repo.get_messages(session.id, 40)) == 2, "сессию помечаем, а не удаляем"


# ── критерий 5: возврат в ТУ ЖЕ корзину ────────────────────────────────────────

async def test_paid_run_is_refunded_as_paid_not_free(billing, repo):
    await billing.start_session(1, slug="a", version="lite")     # сжигает free
    await repo.set_status((await repo.get_active_session(1)).id, "finished")
    await billing.on_successful_payment(1, charge_id="ch1", currency="XTR",
                                        total_amount=100, invoice_payload="run:1")
    await billing.start_session(1, slug="b", version="lite")      # тратит paid
    assert (await repo.get_billing(1))["paid_credits"] == 0

    await repo.abandon_session(1)

    b = await repo.get_billing(1)
    assert b["paid_credits"] == 1, "платный прогон возвращается платным"
    assert b["free_used"] == 1, "free-корзину возврат не трогает"


# ── критерий 6: владельца биллинг не касается — и мы ему не врём ────────────────

async def test_owner_reset_touches_no_billing_and_claims_no_refund(owner_billing, repo):
    await owner_billing.start_session(OWNER, slug="idea", version="lite")
    before = await repo.get_billing(OWNER)

    refunded = await repo.abandon_session(OWNER)

    assert refunded is False, "владельцу нечего возвращать — не говорить «вернулся на счёт»"
    assert await repo.get_billing(OWNER) == before


# ── критерий 9: abandoned освобождает слот активной сессии ─────────────────────

async def test_abandoned_frees_the_active_slot(billing, repo):
    first = await billing.start_session(1, slug="a", version="lite")
    await repo.abandon_session(1)

    second = await billing.start_session(1, slug="b", version="lite")

    assert second is not NEEDS_PAYMENT
    assert second.id != first.id, "новая сессия, а не воскрешение брошенной"
    assert (await repo.get_active_session(1)).id == second.id


# ── C1: гонка abandon ↔ finish. Здесь текут деньги ──────────────────────────────

async def test_finish_after_abandon_does_not_resurrect_the_session(billing, repo, orch):
    """Человек жмёт «начать заново», пока ход ещё идёт. Ход доходит до finish.

    Без условного UPDATE: finish перезапишет abandoned→finished и отдаст spec.md —
    человек получит и спеку, и возвращённый прогон. Повторяемо сколько угодно.
    """
    session = await billing.start_session(1, slug="idea", version="lite")
    await repo.abandon_session(1)
    assert (await repo.get_billing(1))["free_used"] == 0

    ok = await repo.set_status_if_active(session.id, "finished")

    assert ok is False, "брошенную сессию нельзя завершить — спеку не отдавать"
    assert (await repo.get_billing(1))["free_used"] == 0, "и прогон обязан остаться возвращённым"
