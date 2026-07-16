"""Phase 4 — regression guard on the ROOT CAUSE (criterion 8).

The live bug came from step instructions literally ordering 'Задай 5-7 уточняющих вопросов',
which beat the system prompt. No step instruction may demand several questions at once.
"""
import re

from launch11bot.pipeline import steps

# "задай 5-7 вопросов", "предложи 4-5 метафор", "3 варианта ... вопрос" etc.
MULTI_ASK = re.compile(
    r"(зада(й|вай)|спроси|предложи)[^.]{0,40}?\d+\s*[-–—]\s*\d+\s*[^.]{0,20}?(вопрос|метафор)",
    re.IGNORECASE,
)


def test_no_step_instruction_demands_multiple_questions_at_once():
    offenders = []
    for version, plist in steps.PIPELINES.items():
        for s in plist:
            if MULTI_ASK.search(s.instruction):
                offenders.append(f"{version}/{s.id}: {s.instruction[:90]}")
    assert not offenders, "step instructions must not order multi-question dumps:\n" + "\n".join(offenders)


def test_step_instructions_mention_one_at_a_time():
    # every 'Смысл'-zone step (the question-heavy ones) must state the one-question rule
    for version, plist in steps.PIPELINES.items():
        for s in plist:
            if s.zone == "Смысл":
                assert "по одному" in s.instruction.lower() or "ask_question" in s.instruction, \
                    f"{version}/{s.id} must state the one-question-at-a-time contract"
