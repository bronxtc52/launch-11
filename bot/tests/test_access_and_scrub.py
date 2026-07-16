"""Criteria 9, 13 — access gate and Sentry scrubber (pure units)."""
from launch11bot.tg.access import is_allowed
from launch11bot.observability import scrub_event


def test_access_gate():
    allowed = {424242, 42}
    assert is_allowed(42, allowed) is True
    assert is_allowed(999, allowed) is False


def test_access_gate_empty_denies_all():
    assert is_allowed(1, set()) is False


def test_scrub_removes_message_text_and_tokens():
    event = {
        "request": {"data": {"message": {"text": "секрет пользователя"}}},
        "extra": {"bot_token": "123:abc", "api_key": "sk-ant-xyz"},
        "message": "boom 123:abc",
    }
    out = scrub_event(event, None)
    flat = str(out)
    assert "секрет пользователя" not in flat
    assert "sk-ant-xyz" not in flat
    assert "123:abc" not in flat
