"""Phase 2 — Full/Spec-only registry (criteria 1, 2)."""
from launch11bot.pipeline import steps


def test_full_registered_11_steps():
    assert len(steps.step_ids("full")) == 11
    assert steps.first_step_id("full") == "F1"
    assert steps.next_step_id("full", "F11") is None


def test_spec_only_is_slice_8_11():
    assert steps.step_ids("spec_only") == ["F8", "F9", "F10", "F11"]
    assert steps.first_step_id("spec_only") == "F8"


def test_full_zones():
    z = {s.id: s.zone for s in steps.PIPELINES["full"]}
    assert z["F1"] == "Смысл"
    assert z["F8"] == "Bridge"
    assert z["F11"] == "Реализация"


def test_full_steps_have_instructions():
    for s in steps.PIPELINES["full"]:
        assert s.title and s.goal and s.instruction
