"""Criteria 3, 4, 5, 6 — orchestrator FSM over the Repo protocol."""
import pytest
from launch11bot.pipeline.orchestrator import StepError


async def test_start_session_defaults(orch):
    s = await orch.start(201374791, idea_slug="my-idea")
    assert s.version == "lite"
    assert s.current_step == "L1"
    assert s.status == "active"


async def test_save_advances_current_step(orch):
    s = await orch.start(1)
    s = await orch.save_artifact(s, "L1", "# northern star")
    assert s.current_step == "L2"


async def test_cannot_skip_ahead(orch):
    s = await orch.start(1)  # current L1
    with pytest.raises(StepError):
        await orch.save_artifact(s, "L3", "skip")  # future step -> reject


async def test_unknown_step_rejected(orch):
    s = await orch.start(1)
    with pytest.raises(StepError):
        await orch.save_artifact(s, "ZZ", "junk")


async def test_idempotent_resave_overwrites_no_duplicate_no_extra_advance(orch, repo):
    s = await orch.start(1)
    s = await orch.save_artifact(s, "L1", "v1")   # -> L2
    # re-save the already-completed L1: overwrite, must NOT advance further
    s = await orch.save_artifact(s, "L1", "v2")
    arts = await repo.get_artifacts(s.id)
    assert arts["L1"] == "v2"           # overwritten
    assert list(arts).count("L1") == 1  # single row
    assert s.current_step == "L2"       # did not drift to L3


async def test_finish_gate_and_assembly(orch):
    s = await orch.start(1, idea_slug="widget")
    for sid in ["L1", "L2", "L3", "L4"]:
        assert not await orch.can_finish(s)
        s = await orch.save_artifact(s, sid, f"# {sid} body")
    assert await orch.can_finish(s)
    spec = await orch.finish(s)
    # all step bodies present, in order
    assert spec.index("L1 body") < spec.index("L4 body")
    assert "widget" in spec


async def test_finish_rejected_when_incomplete(orch):
    s = await orch.start(1)
    s = await orch.save_artifact(s, "L1", "only one")
    with pytest.raises(StepError):
        await orch.finish(s)


async def test_double_finish_rejected(orch):
    s = await orch.start(1)
    for sid in ["L1", "L2", "L3", "L4"]:
        s = await orch.save_artifact(s, sid, f"# {sid}")
    await orch.finish(s)  # first ok, status -> finished
    with pytest.raises(StepError):
        await orch.finish(s)  # second must be rejected (no duplicate delivery)


async def test_session_byte_cap_enforced(orch):
    s = await orch.start(1)
    orch.settings.max_session_artifact_bytes = 100
    with pytest.raises(StepError):
        await orch.save_artifact(s, "L1", "x" * 200)
    assert s.current_step == "L1"  # rejected, no advance
