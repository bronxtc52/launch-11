"""Phase 4 — the escapes acceptance testing actually proved (criterion 11, hardened).

Each of these got a multi-question dump to the user through the sanctioned channel.
"""
from launch11bot.pipeline.question import (validate_preamble, validate_prose,
                                           validate_question, validate_rendered)
from launch11bot.pipeline.tool_dispatcher import dispatch

DUMP = ("Отлично! Несколько вопросов:\n1. Кто страдает?\n2. Какой костыль сейчас?\n"
        "3. Что бесит больше всего?")


async def test_dump_in_preamble_is_rejected(orch):
    """The killer: dump in preamble, innocent question — reproduced the original bug 1:1."""
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question", {"preamble": DUMP, "question": "Начнём?"})
    assert res.ok is False
    assert s.current_question is None          # nothing stored, nothing sent


async def test_imperative_dump_without_question_mark_is_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"question": "Расскажи про пользователя. Опиши боль. Дай контекст."})
    assert res.ok is False                     # not a question at all -> rejected


async def test_inline_numbering_is_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"question": "Ответь: 1) кто клиент; 2) какая боль; 3) какой рынок?"})
    assert res.ok is False


async def test_unicode_question_marks_are_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"question": "Кто клиент？ Какая боль？ Что бесит？"})
    assert res.ok is False                     # fullwidth '？' normalized before counting


async def test_questions_via_periods_with_one_mark_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"question": "Кто твой пользователь. Какая у него боль. Что он делает "
                                      "сейчас. Сколько платит?"})
    assert res.ok is False                     # too many sentences for one question


async def test_clean_question_with_short_preamble_passes(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"preamble": "Понял, идея ясная.", "question": "Кто страдает без продукта?"})
    assert res.ok is True
    assert res.question == "Понял, идея ясная.\n\nКто страдает без продукта?"
    assert s.current_question == "Кто страдает без продукта?"


def test_prose_validator_lets_honest_text_through():
    # regression: honest prose must NOT be treated as a violation (reviewer HIGH-2)
    assert validate_prose("Отлично, зафиксировал. Идём дальше.") is None
    assert validate_prose("ADR — это запись архитектурного решения.") is None
    # …but a dump in prose is still caught, in either form
    assert validate_prose("Теперь:\n1. Расскажи про X\n2. Опиши Y") is not None
    assert validate_prose("А какая боль?") is not None


def test_validators_directly():
    assert validate_question("Кто страдает?") is None
    assert validate_question("Кто? Какая боль?") is not None
    assert validate_preamble("Коротко и по делу.") is None
    assert validate_preamble("А ты кто?") is not None
    assert validate_rendered("Контекст. Кто страдает?") is None
    assert validate_rendered("Кто? Что?") is not None
