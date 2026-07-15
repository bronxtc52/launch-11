"""Phase 2 — assembly with ADR + spec_only slice (criteria 7, 8)."""
from launch11bot.pipeline.assemble import assemble_spec


def test_full_assembly_orders_steps_and_appends_adr():
    arts = {f"F{i}": f"body{i}" for i in range(1, 12)}
    adrs = [
        {"n": 1, "title": "База данных", "markdown": "выбрали Postgres"},
        {"n": 2, "title": "Авторизация", "markdown": "JWT"},
    ]
    spec = assemble_spec("prod", "full", arts, adrs)
    # ordering: headers appear F1..F11 in order (avoid body1⊂body11 substring trap)
    positions = [spec.index(f"## F{i}.") for i in range(1, 12)]
    assert positions == sorted(positions)
    assert "Решения (ADR)" in spec
    assert "ADR-1" in spec and "выбрали Postgres" in spec
    assert "ADR-2" in spec


def test_full_assembly_without_adr_has_no_adr_section():
    arts = {f"F{i}": f"b{i}" for i in range(1, 12)}
    spec = assemble_spec("p", "full", arts)  # adrs default None
    assert "Решения (ADR)" not in spec


def test_spec_only_slice_excludes_steps_1_7():
    # feed ALL F1..F11 — assembly must still emit only the spec_only slice (F8..F11),
    # proving it iterates the pipeline, not the artifact dict (tester's completeness note)
    arts = {f"F{i}": f"body{i}" for i in range(1, 12)}
    spec = assemble_spec("p", "spec_only", arts)
    assert "## F8." in spec and "## F11." in spec
    for i in range(1, 8):
        assert f"## F{i}." not in spec  # headers are unambiguous (body1⊂body11 otherwise)
