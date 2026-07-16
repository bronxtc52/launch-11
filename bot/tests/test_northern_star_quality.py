"""Northern Star must be offered as FULL SENTENCES, derived from the human's answers.

Live: the bot offered «скорость, регулярность или доля нанятых» — focus LABELS, not Northern
Stars. The methodology (claude-ai/SKILL.md) is explicit: a Northern Star is ONE SENTENCE about
success («Новый партнёр выходит на первую продажу за 14 дней»), never a word.

Root was in my own text: the F1 instruction said «предложи 3 варианта с фокусами
(скорость / регулярность / результат)» — the model faithfully offered the focuses. The
`options` schema then told it to list «точными короткими словами», reinforcing the label habit.
"""
import re

from launch11bot.llm import tools
from launch11bot.pipeline import steps

STAR_STEPS = {"L1", "F1"}  # the steps that produce the Northern Star


def _star_instructions():
    out = []
    for plist in steps.PIPELINES.values():
        for s in plist:
            if s.id in STAR_STEPS:
                out.append((s.id, s.instruction))
    return out


def test_star_steps_demand_a_full_sentence_not_a_label():
    for sid, instr in _star_instructions():
        low = instr.lower()
        assert "предложени" in low, \
            f"{sid}: инструкция обязана требовать ПОЛНОЕ ПРЕДЛОЖЕНИЕ, а не ярлык"


def test_star_steps_forbid_offering_bare_focus_words():
    """Регресс-гвард на корень: «предложи 3 варианта с фокусами (скорость/регулярность/…)»
    прямо провоцировал модель выдавать ярлыки."""
    bad = re.compile(r"вариант[а-я]*\s+[^.]{0,30}с\s+фокусами", re.IGNORECASE)
    for sid, instr in _star_instructions():
        assert not bad.search(instr), f"{sid}: формулировка провоцирует выдавать фокусы-ярлыки"


def test_star_steps_carry_a_concrete_good_example():
    """Модель должна видеть эталон, а не абстрактное требование."""
    for sid, instr in _star_instructions():
        assert "например" in instr.lower() or "«" in instr, \
            f"{sid}: нужен конкретный пример хорошей Northern Star"


def test_star_steps_state_it_is_derived_from_the_answers():
    for sid, instr in _star_instructions():
        low = instr.lower()
        assert "ответ" in low, f"{sid}: звезда выводится ИЗ ОТВЕТОВ человека, не из воздуха"


def test_options_schema_does_not_push_short_labels():
    """`options` нужны коду для засчитывания выбора — но они не должны подменять собой
    полноценные формулировки в тексте вопроса."""
    defs = {t["name"]: t for t in tools.tool_defs("full")}
    desc = defs["ask_question"]["input_schema"]["properties"]["options"]["description"]
    assert "короткими словами" not in desc, \
        "описание options само учило модель предлагать ярлыки вместо формулировок"
    assert "preamble" in desc.lower(), \
        "options должны требовать, чтобы полные формулировки были показаны человеку"
