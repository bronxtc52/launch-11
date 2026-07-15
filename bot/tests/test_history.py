"""Review finding #1 — valid Anthropic history construction."""
from launch11bot.llm.history import normalize_history


def test_drops_leading_assistant():
    msgs = [("assistant", "greeting"), ("user", "hi"), ("assistant", "reply")]
    h = normalize_history(msgs, 40)
    assert h[0]["role"] == "user"


def test_coalesces_consecutive_same_role():
    msgs = [("user", "a"), ("assistant", "x"), ("assistant", "y"), ("user", "b")]
    h = normalize_history(msgs, 40)
    roles = [m["role"] for m in h]
    # no two same-role in a row after coalescing
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
    assert "x\n\ny" in h[1]["content"]


def test_window_then_still_starts_with_user():
    msgs = [("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(100)]
    h = normalize_history(msgs, 40)
    assert len(h) <= 40
    assert h[0]["role"] == "user"
    roles = [m["role"] for m in h]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
