"""THE invariant (fusion verdict): the model may DELAY progress, never STOP it.

No sequence of model decisions may trap a human. The number of delays per open question is
bounded by code, persisted, and NOT reset by a re-ask. There is exactly ONE branch for every
non-`answer` verdict — no `if verdict == "partial"` special cases, so a future verdict type
cannot open a new trap.
"""
import pytest
from launch11bot.pipeline.orchestrator import StepError
from launch11bot.pipeline.tool_dispatcher import dispatch

Q = "Какой фокус ближе — скорость, регулярность или результат?"


# ---------- the live symptom: a closed choice is judged by CODE, not by the model ----------

async def test_picking_an_offered_option_is_accepted_even_if_model_says_partial(orch, repo):
    """Живой баг: бот предложил 3 варианта, человек ответил «Скорость», модель сказала
    partial → вечная петля. Код обязан признать выбор сам."""
    s = await orch.start(1)
    await orch.ask_question(s, Q, options=["скорость", "регулярность", "результат"])
    res = await dispatch(orch, s, "assess_answer", {"verdict": "partial", "missing": "не уточнил"})
    # code overrides: the reply matches an offered option
    decision = await orch.resolve_answer(s, "Скорость", verdict="partial")
    assert decision.terminal is True
    assert decision.reason == "deterministic_choice_match"
    assert s.current_question is None, "выбор принят — вопрос закрыт"


async def test_choice_match_is_case_and_form_insensitive(orch):
    s = await orch.start(1)
    await orch.ask_question(s, Q, options=["скорость", "регулярность", "результат"])
    d = await orch.resolve_answer(s, "  СКОРОСТЬ  ", verdict="offtopic")
    assert d.terminal is True and d.reason == "deterministic_choice_match"


async def test_free_text_question_still_goes_through_the_model(orch):
    s = await orch.start(1)
    await orch.ask_question(s, "Кто страдает без продукта?")  # no options -> not a choice
    d = await orch.resolve_answer(s, "рекрутер", verdict="answer")
    assert d.terminal is True and d.reason == "llm_answer"


# ---------- the invariant itself ----------

async def test_clarify_budget_bounds_any_verdict(orch, repo):
    """ЕДИНАЯ ветка: partial, offtopic и любой будущий тип тратят один бюджет."""
    s = await orch.start(1)
    await orch.ask_question(s, "Опиши боль?")
    for verdict in ("partial", "offtopic", "partial"):  # mixed on purpose
        d = await orch.resolve_answer(s, "ответ", verdict=verdict)
        if not d.terminal:
            await orch.ask_question(s, "уточни?")       # re-ask must NOT reset the counter
    d = await orch.resolve_answer(s, "ответ", verdict="partial")
    assert d.terminal is True, "бюджет исчерпан — код обязан сдвинуться сам"
    assert d.reason == "clarify_budget_exhausted"


async def test_reask_does_not_reset_the_counter(orch, repo):
    """ask_question сбрасывал last_verdict в NULL → серия становилась невидимой."""
    s = await orch.start(1)
    await orch.ask_question(s, "Вопрос?")
    await orch.resolve_answer(s, "x", verdict="partial")
    n1 = s.clarify_count
    await orch.ask_question(s, "Переформулированный вопрос?")
    assert s.clarify_count == n1, "переспрос НЕ обнуляет счётчик задержек"


async def test_no_sequence_of_model_decisions_can_trap_the_user(orch, repo):
    """Главный инвариант: сколько бы модель ни занижала вердикт — прогресс наступит."""
    s = await orch.start(1)
    await orch.ask_question(s, "Вопрос?")
    for i in range(20):  # модель упорствует
        d = await orch.resolve_answer(s, "мой ответ", verdict="partial")
        if d.terminal:
            break
        await orch.ask_question(s, f"уточнение {i}?")
    else:
        pytest.fail("модель заперла человека — инвариант нарушен")
    assert s.clarify_count <= s.clarify_budget


async def test_force_close_marks_the_artifact_and_keeps_raw_answer(orch, repo):
    """Принудительный сдвиг не притворяется, что ответ полный."""
    s = await orch.start(1)
    await orch.ask_question(s, "Вопрос?")
    for _ in range(s.clarify_budget):
        await orch.resolve_answer(s, "мой ответ", verdict="partial")
        await orch.ask_question(s, "ещё?")
    d = await orch.resolve_answer(s, "мой ответ", verdict="partial")
    assert d.terminal and d.reason == "clarify_budget_exhausted"
    assert d.status == "partial", "статус отражает реальность, а не притворяется complete"
    assert "мой ответ" in (d.raw_answer or ""), "сырой ответ человека сохраняется"


# ---------- explicit human intents beat any model verdict ----------

async def test_dont_know_is_a_legitimate_terminal_outcome(orch):
    s = await orch.start(1)
    await orch.ask_question(s, "Сколько кандидатов в месяц?")
    d = await orch.resolve_answer(s, "не знаю", verdict="partial")
    assert d.terminal is True and d.status == "unknown"
    assert d.reason == "user_said_unknown", "«не знаю» не должно молча жечь бюджет"


# ---------- verdict loses its blocking power ----------

async def test_partial_no_longer_hard_blocks_save_artifact(orch):
    """`partial` больше не запрет, а вход контроллера (fusion: C — право перехода у кода)."""
    s = await orch.start(1)
    await orch.ask_question(s, "Вопрос?")
    await orch.resolve_answer(s, "ответ", verdict="answer")   # controller says terminal
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": "# ok"})
    assert res.ok is True


def test_no_verdict_specific_branch_remains():
    """Регресс-гвард против whack-a-mole: в коде перехода не должно быть спецветки по значению."""
    import inspect
    from launch11bot.pipeline import orchestrator
    src = inspect.getsource(orchestrator.Orchestrator.resolve_answer)
    assert 'verdict == "partial"' not in src, "спецслучай по значению вердикта вернулся"
    assert 'verdict == "offtopic"' not in src, "спецслучай по значению вердикта вернулся"
