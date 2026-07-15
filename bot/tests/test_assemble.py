"""Criterion 6 — spec assembly."""
from launch11bot.pipeline.assemble import assemble_spec


def test_assemble_orders_and_titles():
    arts = {"L2": "b body", "L1": "a body", "L4": "d body", "L3": "c body"}
    spec = assemble_spec("cool-idea", "lite", arts)
    assert spec.startswith("#")
    assert "cool-idea" in spec
    # ordered L1..L4 regardless of dict insertion order
    assert spec.index("a body") < spec.index("b body") < spec.index("c body") < spec.index("d body")


def test_assemble_skips_missing_steps_gracefully():
    spec = assemble_spec("x", "lite", {"L1": "only"})
    assert "only" in spec
