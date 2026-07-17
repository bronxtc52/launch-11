"""The user must never be left not knowing what is expected of them.

Live: the bot sent a 1264-char L4 dump ending mid-item («4. Интеграция поиска кандидатов»)
with NO question. DB: current_question = NULL. Cause: max_tokens=2000 cut the model off
mid-generation, so it never reached its ask_question call — and the truncated prose was
forwarded anyway, because it contained no '?' and my validator only looks for questions.

Two guarantees, both owned by code:
  1. a truncated model response is NEVER forwarded to the human;
  2. a turn never ends leaving the human with nothing to answer.
"""
from launch11bot.app.turn import run_user_turn
from launch11bot.llm.client import Turn


class FakeClaude:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def turn(self, system, history, version, **_):
        self.calls += 1
        return self.script.pop(0) if self.script else Turn(text="")


async def _noop(*a):
    pass


async def _run(orch, repo, s, claude, user_text="да"):
    sent_q, sent_t = [], []

    async def on_q(q):
        sent_q.append(q)

    async def on_t(t):
        sent_t.append(t)

    await run_user_turn(orch=orch, claude=claude, repo=repo, settings=orch.settings, session=s,
                        user_text=user_text, on_text=on_t, on_document=_noop, on_notice=_noop,
                        on_question=on_q)
    return sent_q, sent_t


TRUNCATED = ("Финальный шаг — L4. Northern Star: ИИ выходит на связь кратно быстрее.\n"
             "Задачи v1:\n1. Настроить FastAPI. DoD: health-check 200.\n"
             "2. Модели данных. DoD: миграции.\n4. Интеграция поиска кандидатов")


async def test_truncated_response_is_never_forwarded(orch, repo):
    s = await orch.start(1)
    claude = FakeClaude([
        Turn(text=TRUNCATED, stop_reason="max_tokens"),      # cut off mid-generation
        Turn(text="Коротко: контекст собран.",
             tool_calls=[("t1", "ask_question", {"question": "Подтверждаешь?"})]),
    ])
    sent_q, sent_t = await _run(orch, repo, s, claude)

    assert TRUNCATED not in " ".join(sent_t), "обрезанный ответ нельзя пересылать человеку"
    assert claude.calls == 2, "обрезку надо переспросить, а не отдать как есть"
    assert sent_q == ["Подтверждаешь?"]


async def test_turn_never_ends_without_something_to_answer(orch, repo):
    """Модель высказалась прозой и не задала вопрос — человек не знает, что от него нужно."""
    s = await orch.start(1)
    claude = FakeClaude([Turn(text="Вот весь контекст и задачи. Всё готово.")])
    sent_q, sent_t = await _run(orch, repo, s, claude)

    everything = " ".join(sent_t + sent_q)
    assert "?" in everything, "ход обязан закончиться тем, на что человек может ответить"


async def test_a_question_asked_means_no_extra_nudge(orch, repo):
    """Гвард не должен тарахтеть, когда вопрос уже задан."""
    s = await orch.start(1)
    claude = FakeClaude([Turn(text="Контекст собран.",
                              tool_calls=[("t1", "ask_question", {"question": "Подтверждаешь?"})])])
    sent_q, sent_t = await _run(orch, repo, s, claude)
    assert sent_q == ["Подтверждаешь?"]
    assert len([t for t in sent_t if "?" in t]) == 0


def test_max_tokens_fits_a_real_artifact():
    from launch11bot.config import Settings
    field = Settings.model_fields["claude_max_tokens"]
    assert field.default >= 4096, \
        "2000 токенов не вмещают артефакт L4 — модель обрывало на полуслове"
