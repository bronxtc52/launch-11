"""Доставка спеки идемпотентна: статус гейтит ДЕНЬГИ, а не выдачу.

Находка C-1 (ревью плана v2, опаснее исходного бага): finish ставил `finished` и коммитил, а
спека уходила в on_document ПОСЛЕ. Telegram чихнул → спеки нет; reset не вернёт (WHERE
status='active'); resume не найдёт → /start создаёт новую сессию → пейволл. А finish навсегда
отвечал «сессия уже завершена» — и условный UPDATE делал этот гард ПЕРСИСТЕНТНЫМ: спека
недостижима вообще никогда.

Тот же инцидент, сдвинутый на 30 секунд вправо: человек снова платит за наш сбой.
"""
import pytest
from launch11bot.billing.service import BillingService
from launch11bot.pipeline.orchestrator import StepError


@pytest.fixture
def billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")


async def _completed_session(billing, repo, orch):
    """Сессия, прошедшая пайплайн: артефакты на всех шагах, finish ещё не звали."""
    from launch11bot.pipeline import steps
    session = await billing.start_session(1, slug="idea", version="lite")
    for st in steps.PIPELINES["lite"]:
        await repo.save_artifact(session.id, st.id, f"## {st.title}\n\nсодержимое")
    await repo.advance_step(session.id, session.current_step, "_finish")
    return await repo.get_active_session(1)


# ── C-1: провал доставки не должен стоить человеку прогона ──────────────────────

async def test_spec_is_redeliverable_after_a_failed_send(billing, repo, orch):
    """Спека собрана и статус закрыт, но Telegram упал. Спека обязана остаться доступной."""
    session = await _completed_session(billing, repo, orch)
    first = await orch.finish(session)          # статус → finished, спека «отправлена»
    assert first

    again = await orch.finish(await repo.get_active_session(1) or session)

    assert again == first, "finish на finished пересобирает и отдаёт спеку, а не StepError"


async def test_finish_assembles_before_closing_the_session(billing, repo, orch):
    """Порядок: can_finish → assemble → условный UPDATE → return.

    Обратный порядок даёт `finished` без спеки и без возврата — деньги списаны, ценности нет.
    """
    session = await _completed_session(billing, repo, orch)
    boom = RuntimeError("assemble упал")

    import launch11bot.pipeline.assemble as assemble_mod
    orig = assemble_mod.assemble_spec
    assemble_mod.assemble_spec = lambda *a, **k: (_ for _ in ()).throw(boom)
    try:
        with pytest.raises(RuntimeError):
            await orch.finish(session)
    finally:
        assemble_mod.assemble_spec = orig

    assert (await repo.get_active_session(1)) is not None, \
        "сборка упала — сессия обязана остаться активной (иначе ни спеки, ни возврата)"


async def test_incomplete_pipeline_still_cannot_finish(billing, repo, orch):
    """Идемпотентная выдача не должна открыть выдачу недоделанной спеки."""
    session = await billing.start_session(1, slug="idea", version="lite")
    with pytest.raises(StepError):
        await orch.finish(session)
