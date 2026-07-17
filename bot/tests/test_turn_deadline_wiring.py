"""Дедлайн должен быть ПОДКЛЮЧЁН, а не просто написан.

Ревью реализации: дедлайн жил в llm/client.py, но turn.py звал claude.turn(system, history,
version) без него → deadline=None в проде → все ветки бюджета мертвы → 6 попыток × 90с + паузы
≈ 571с на вызов × 6 итераций tool-loop = ~57 минут молчания. Хуже, чем 48 минут v1, которые мы
сами забраковали.

Юнит-тест клиента этого не ловил: он передавал deadline напрямую, минуя проводку. Тест проверял
деталь, а не то, что она включена. Этот тест смотрит на run_user_turn — то, что реально бежит.
"""
import asyncio

import pytest
from launch11bot.app.turn import run_user_turn
from launch11bot.llm.client import ClaudeOverloaded


class FakeSettings:
    max_context_messages = 40
    claude_max_tokens = 8000
    claude_timeout_s = 90.0
    max_artifact_bytes = 20000
    max_session_artifact_bytes = 200000
    turn_budget_s = 120.0
    beta_allowlist = set()


class OverloadedClaude:
    """Двойник Anthropic в перегрузке: считает попытки и никогда не отвечает."""
    def __init__(self):
        self.calls = 0
        self.deadlines = []

    async def turn(self, system, history, version, *, deadline=None, on_wait=None):
        self.calls += 1
        self.deadlines.append(deadline)
        raise ClaudeOverloaded("overloaded")


async def test_turn_passes_a_deadline_to_the_client(repo, orch):
    """Без дедлайна клиент молчит ~57 минут на одно сообщение человека."""
    session = await orch.start(1)
    claude = OverloadedClaude()
    said = []

    with pytest.raises(ClaudeOverloaded):
        await run_user_turn(
            orch=orch, claude=claude, repo=repo, settings=FakeSettings(),
            session=session, user_text="моя идея",
            on_text=lambda t: said.append(t), on_document=None,
            on_notice=lambda m: None, on_question=lambda q: said.append(q),
        )

    assert claude.deadlines, "claude.turn вообще не звали"
    assert claude.deadlines[0] is not None, "дедлайн не подключён — бюджет хода мёртв"


async def test_deadline_is_shared_across_the_tool_loop(repo, orch):
    """Один бюджет на ход, а не свежие 90с на каждой из 6 итераций tool-loop."""
    session = await orch.start(1)
    claude = OverloadedClaude()

    with pytest.raises(ClaudeOverloaded):
        await run_user_turn(
            orch=orch, claude=claude, repo=repo, settings=FakeSettings(),
            session=session, user_text="моя идея",
            on_text=lambda t: None, on_document=None,
            on_notice=lambda m: None, on_question=lambda q: None,
        )

    assert len(set(claude.deadlines)) <= 1, \
        f"дедлайн обязан быть общим на ход, получили {claude.deadlines}"


async def test_deadline_is_within_the_configured_budget(repo, orch):
    session = await orch.start(1)
    claude = OverloadedClaude()
    now = asyncio.get_running_loop().time()

    with pytest.raises(ClaudeOverloaded):
        await run_user_turn(
            orch=orch, claude=claude, repo=repo, settings=FakeSettings(),
            session=session, user_text="идея",
            on_text=lambda t: None, on_document=None,
            on_notice=lambda m: None, on_question=lambda q: None,
        )

    assert claude.deadlines[0] <= now + FakeSettings.turn_budget_s + 1


def test_turn_budget_is_a_real_setting():
    """turn_budget_s жил только в FakeSettings тестов — поле-декорация, которое никто не читал."""
    from launch11bot.config import Settings
    assert "turn_budget_s" in Settings.model_fields
