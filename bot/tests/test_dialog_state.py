"""Phase 4 — ask_question / assess_answer state + gating (criteria 1,2,4,5,11,14,15)."""
import pytest
from launch11bot.llm import tools
from launch11bot.pipeline.orchestrator import StepError
from launch11bot.pipeline.tool_dispatcher import dispatch


def test_tool_schemas_present():
    defs = {t["name"]: t for t in tools.tool_defs("lite")}
    assert "ask_question" in defs and "assess_answer" in defs
    assert "question" in defs["ask_question"]["input_schema"]["required"]
    enum = defs["assess_answer"]["input_schema"]["properties"]["verdict"]["enum"]
    assert set(enum) == {"answer", "partial", "offtopic"}


async def test_ask_question_stores_current_question(orch, repo):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question", {"question": "Кто страдает без продукта?"})
    assert res.ok is True
    assert res.question == "Кто страдает без продукта?"
    assert res.terminal is True                       # criterion 12: ends the turn
    assert s.current_question == "Кто страдает без продукта?"
    # NOTE: InMemoryRepo hands back the same Session object, so this cannot prove the
    # storage contract — the real persistence check is test_persistence_pg.py, which now
    # actually runs in CI (see .github/workflows/tests.yml) instead of silently skipping.
    assert (await repo.get_active_session(1)).current_question == "Кто страдает без продукта?"


async def test_ask_question_rejects_multi_question_dump(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "ask_question",
                         {"question": "Кто пользователь? Какая боль? Что сейчас делает?"})
    assert res.ok is False                            # criterion 11
    assert s.current_question is None                 # nothing stored, nothing sent


async def test_assess_answer_answer_clears_question(orch):
    s = await orch.start(1)
    await dispatch(orch, s, "ask_question", {"question": "Кто страдает?"})
    res = await dispatch(orch, s, "assess_answer", {"verdict": "answer"})
    assert res.ok is True and res.verdict == "answer"
    assert s.current_question is None                  # criterion 5


async def test_partial_blocks_save_artifact(orch):
    s = await orch.start(1)
    await dispatch(orch, s, "ask_question", {"question": "Кто страдает?"})
    await dispatch(orch, s, "assess_answer", {"verdict": "partial", "missing": "не назвал роль"})
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": "# рано"})
    assert res.ok is False                             # criterion 4
    assert s.current_step == "L1"                      # did not advance


async def test_answer_allows_save_artifact(orch):
    s = await orch.start(1)
    await dispatch(orch, s, "ask_question", {"question": "Кто страдает?"})
    await dispatch(orch, s, "assess_answer", {"verdict": "answer"})
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": "# ok"})
    assert res.ok is True                              # criterion 5
    assert s.current_step == "L2"


async def test_bad_verdict_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "assess_answer", {"verdict": "totally_fine"})
    assert res.ok is False                             # criterion 15


async def test_skip_clears_question_and_unblocks(orch):
    s = await orch.start(1)
    await dispatch(orch, s, "ask_question", {"question": "Кто страдает?"})
    await dispatch(orch, s, "assess_answer", {"verdict": "partial", "missing": "x"})
    await orch.skip_question(s)                        # criterion 14 — user escape (/skip)
    assert s.current_question is None
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": "# ok"})
    assert res.ok is True
