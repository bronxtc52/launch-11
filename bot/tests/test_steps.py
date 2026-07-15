"""Versioned pipeline registry (council A5)."""
from launch11bot.pipeline import steps


def test_lite_registered():
    assert "lite" in steps.PIPELINES
    ids = steps.step_ids("lite")
    assert ids == ["L1", "L2", "L3", "L4"]


def test_first_and_next():
    assert steps.first_step_id("lite") == "L1"
    assert steps.next_step_id("lite", "L1") == "L2"
    assert steps.next_step_id("lite", "L4") is None


def test_get_step_returns_none_for_unknown():
    assert steps.get_step("lite", "ZZ") is None
    assert steps.get_step("lite", "L2").title
