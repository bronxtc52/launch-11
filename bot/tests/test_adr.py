"""Phase 2 — ADR creation (criterion 6)."""
from launch11bot.pipeline.tool_dispatcher import dispatch


async def test_create_adr_numbers_sequentially(orch, repo):
    s = await orch.start(1, version="full")
    r1 = await dispatch(orch, s, "create_adr", {"title": "выбор БД", "markdown": "взяли Postgres"})
    r2 = await dispatch(orch, s, "create_adr", {"title": "auth", "markdown": "JWT"})
    assert r1.ok and r2.ok
    adrs = await repo.get_adrs(s.id)
    assert [a["n"] for a in adrs] == [1, 2]
    assert adrs[0]["title"] == "выбор БД"
    assert adrs[1]["markdown"] == "JWT"


async def test_create_adr_requires_title_and_markdown(orch):
    s = await orch.start(1, version="full")
    res = await dispatch(orch, s, "create_adr", {"title": "no body"})
    assert res.ok is False


async def test_create_adr_bounds_oversize(orch):
    s = await orch.start(1, version="full")
    huge = "x" * (orch.settings.max_artifact_bytes + 1)
    res = await dispatch(orch, s, "create_adr", {"title": "big", "markdown": huge})
    assert res.ok is False
