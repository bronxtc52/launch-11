"""Phase 2 — finish gate for Full requires all 11 steps (criterion 9)."""
import pytest
from launch11bot.pipeline.orchestrator import StepError


async def test_full_finish_requires_all_11(orch):
    s = await orch.start(1, version="full")
    for i in range(1, 11):  # F1..F10 only
        s = await orch.save_artifact(s, f"F{i}", f"body{i}")
    assert not await orch.can_finish(s)
    with pytest.raises(StepError):
        await orch.finish(s)
    s = await orch.save_artifact(s, "F11", "body11")  # the 11th
    assert await orch.can_finish(s)
    spec = await orch.finish(s)
    assert "body11" in spec
