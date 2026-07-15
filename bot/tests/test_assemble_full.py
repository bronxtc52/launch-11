"""Phase 2 — assembly with ADR + spec_only slice (criteria 7, 8)."""
from launch11bot.pipeline.assemble import assemble_spec


def test_full_assembly_orders_steps_and_appends_adr():
    arts = {f"F{i}": f"body{i}" for i in range(1, 12)}
    adrs = [
        {"n": 1, "title": "База данных", "markdown": "выбрали Postgres"},
        {"n": 2, "title": "Авторизация", "markdown": "JWT"},
    ]
    spec = assemble_spec("prod", "full", arts, adrs)
    assert spec.index("body1") < spec.index("body11")
    assert "Решения (ADR)" in spec
    assert "ADR-1" in spec and "выбрали Postgres" in spec
    assert "ADR-2" in spec


def test_full_assembly_without_adr_has_no_adr_section():
    arts = {f"F{i}": f"b{i}" for i in range(1, 12)}
    spec = assemble_spec("p", "full", arts)  # adrs default None
    assert "Решения (ADR)" not in spec


def test_spec_only_slice_excludes_steps_1_7():
    arts = {f"F{i}": f"body{i}" for i in range(8, 12)}
    spec = assemble_spec("p", "spec_only", arts)
    assert "## F8." in spec
    assert "## F1." not in spec and "## F7." not in spec
