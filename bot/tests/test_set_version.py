"""Phase 2 — version selection & switching (criteria 3, 4, 5)."""
from launch11bot.llm import tools
from launch11bot.pipeline.tool_dispatcher import dispatch


def test_set_version_enum_all_three():
    defs = {t["name"]: t for t in tools.tool_defs("lite")}
    enum = defs["set_version"]["input_schema"]["properties"]["version"]["enum"]
    assert set(enum) == {"lite", "full", "spec_only"}


async def test_start_with_version_sets_first_step(orch):
    s = await orch.start(1, version="full")
    assert s.version == "full"
    assert s.current_step == "F1"
    s2 = await orch.start(2, version="spec_only")
    assert s2.current_step == "F8"


async def test_set_version_on_empty_switches_and_resets(orch):
    s = await orch.start(1)  # lite, empty
    res = await dispatch(orch, s, "set_version", {"version": "full"})
    assert res.ok is True
    assert res.session.version == "full"
    assert res.session.current_step == "F1"


async def test_set_version_rejected_when_artifacts_exist(orch):
    s = await orch.start(1)
    s = await orch.save_artifact(s, "L1", "x")  # now non-empty, at L2
    res = await dispatch(orch, s, "set_version", {"version": "full"})
    assert res.ok is False
    assert res.session.version == "lite"
    assert res.session.current_step == "L2"


async def test_dispatch_accepts_each_version_on_empty(orch):
    s = await orch.start(1)
    for v in ["full", "spec_only", "lite"]:
        r = await dispatch(orch, s, "set_version", {"version": v})
        assert r.ok is True
        s = r.session
        assert s.version == v
