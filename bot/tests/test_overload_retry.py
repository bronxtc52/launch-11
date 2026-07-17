"""Переживание перегрузки Claude + честный текст.

Инцидент 2026-07-17: Anthropic отдавал 529 семь минут (30 отказов). Наш ретрай крутил 3 попытки
БЕЗ единого sleep — ~9 запросов за ~5 секунд, и сдавались. Против семиминутного окна это
проигрыш по построению, плюс мы долбили API ровно тогда, когда он просил не долбить.
"""
import asyncio

import pytest
from launch11bot.llm.client import ClaudeClient, ClaudeOverloaded


class FakeSettings:
    launch11_model = "claude-sonnet-5"
    claude_max_tokens = 8000
    claude_timeout_s = 90.0
    claude_max_retries = 2
    turn_budget_s = 120.0

    class _Key:
        @staticmethod
        def get_secret_value():
            return "sk-ant-test"

    anthropic_api_key = _Key()


class FakeStatusError(Exception):
    """Двойник anthropic.APIStatusError — нам важен только status_code."""
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.response = None
        super().__init__(f"HTTP {status_code}")


@pytest.fixture
def slept(monkeypatch):
    """Фейковые часы: тест не должен спать реально, но обязан видеть паузы."""
    calls: list[float] = []

    async def fake_sleep(d):
        calls.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return calls


def _client(monkeypatch, raises):
    c = ClaudeClient(FakeSettings())

    async def boom(**kwargs):
        raise raises()

    monkeypatch.setattr(c._client.messages, "create", boom)
    return c


# ── критерий 7: паузы растут, а не сгорают за 5 секунд ──────────────────────────

async def test_overload_is_retried_with_growing_backoff(monkeypatch, slept):
    c = _client(monkeypatch, lambda: FakeStatusError(529))

    with pytest.raises(ClaudeOverloaded):
        await c.turn(system="s", history=[{"role": "user", "content": "x"}], version="lite")

    assert len(slept) >= 3, "должны быть настоящие паузы, а не тесный цикл"
    assert slept == sorted(slept), f"паузы обязаны расти, получили {slept}"
    assert sum(slept) >= 30, f"бюджет ретраев ≥30с, получили {sum(slept):.1f}с"


async def test_429_is_retried_like_overload(monkeypatch, slept):
    c = _client(monkeypatch, lambda: FakeStatusError(429))
    with pytest.raises(ClaudeOverloaded):
        await c.turn(system="s", history=[{"role": "user", "content": "x"}], version="lite")
    assert slept, "429 — тоже «подожди», а не «сдавайся»"


async def test_503_is_retried(monkeypatch, slept):
    """max_retries=0 у SDK: если не ретраить весь 5xx сами — 503 упадёт с первой секунды.

    Тихая регрессия: сейчас 5xx глушит SDK, а мы его выключаем.
    """
    c = _client(monkeypatch, lambda: FakeStatusError(503))
    with pytest.raises(ClaudeOverloaded):
        await c.turn(system="s", history=[{"role": "user", "content": "x"}], version="lite")
    assert slept, "503 обязан ретраиться"


async def test_asyncio_timeout_is_retried(monkeypatch, slept):
    """asyncio.wait_for поднимает asyncio.TimeoutError, а НЕ anthropic.APITimeoutError.

    Сейчас его ретраит голый `except Exception`. Забыть его при разборе классов = регрессия.
    """
    c = _client(monkeypatch, lambda: asyncio.TimeoutError())
    with pytest.raises(ClaudeOverloaded):
        await c.turn(system="s", history=[{"role": "user", "content": "x"}], version="lite")
    assert slept, "таймаут обязан ретраиться"


# ── не ретраить то, что ретраить бессмысленно ──────────────────────────────────

@pytest.mark.parametrize("code", [400, 401, 403])
async def test_client_errors_are_not_retried(monkeypatch, slept, code):
    c = _client(monkeypatch, lambda: FakeStatusError(code))

    with pytest.raises(Exception) as e:
        await c.turn(system="s", history=[{"role": "user", "content": "x"}], version="lite")

    assert not isinstance(e.value, ClaudeOverloaded)
    assert slept == [], f"{code} не чинится ожиданием — поднимать сразу"


# ── критерий 8 / C-2: дедлайн реально ограничивает ход ─────────────────────────

async def test_deadline_stops_retrying(monkeypatch, slept):
    """Дедлайн проверяется перед КАЖДОЙ попыткой, включая первую.

    v2 проверял только перед повторной → 6 итераций tool-loop × свежие 90с = 540с молчания.
    """
    c = _client(monkeypatch, lambda: FakeStatusError(529))
    past = asyncio.get_event_loop().time() - 1  # дедлайн уже истёк

    with pytest.raises(ClaudeOverloaded):
        await c.turn(system="s", history=[{"role": "user", "content": "x"}],
                     version="lite", deadline=past)

    assert slept == [], "дедлайн истёк — не спать и не слать запрос"


async def test_sdk_retries_are_disabled(monkeypatch):
    """max_retries=0: иначе наши попытки умножаются на SDK-шные (было ~90 запросов на ход)."""
    c = ClaudeClient(FakeSettings())
    assert c._client.max_retries == 0
