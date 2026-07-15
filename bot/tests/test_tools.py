"""Criteria 7, 10, 11 — tool schemas + dispatcher."""
import pytest
from launch11bot.llm import tools
from launch11bot.pipeline.tool_dispatcher import dispatch


def test_tool_defs_step_enum():
    defs = {t["name"]: t for t in tools.tool_defs("lite")}
    assert set(defs) >= {"save_artifact", "set_version", "finish"}
    assert defs["save_artifact"]["input_schema"]["properties"]["step_id"]["enum"] == ["L1", "L2", "L3", "L4"]
    # set_version enum is covered by tests/test_set_version.py (Phase 2 allows all three)


async def test_unknown_tool_is_safe_not_crash(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "delete_everything", {})
    assert res.ok is False
    assert res.session.current_step == "L1"  # unchanged


async def test_set_version_lite_accepted(orch):
    # Phase 2: set_version now accepts full/spec_only too — see test_set_version.py
    s = await orch.start(1)
    ok = await dispatch(orch, s, "set_version", {"version": "lite"})
    assert ok.ok is True
    assert ok.session.current_step == "L1"


async def test_save_artifact_bounds_reject_oversize(orch):
    s = await orch.start(1)
    huge = "x" * (orch.settings.max_artifact_bytes + 1)
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": huge})
    assert res.ok is False
    assert res.session.current_step == "L1"  # did not advance


async def test_save_artifact_unknown_step_rejected(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L9", "markdown": "hi"})
    assert res.ok is False


async def test_save_artifact_happy_path_advances(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "save_artifact", {"step_id": "L1", "markdown": "# ok"})
    assert res.ok is True
    assert res.session.current_step == "L2"
