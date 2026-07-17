"""Phase 4 — turn-service dialogue discipline (criteria 3, 6, 7, 12, 13)."""
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


def _cbs():
    sent_text, sent_q = [], []

    async def on_text(t):
        sent_text.append(t)

    async def on_question(q):
        sent_q.append(q)

    return sent_text, sent_q, on_text, on_question


async def _run(orch, repo, session, claude, on_text, on_question, user_text="ответ"):
    return await run_user_turn(
        orch=orch, claude=claude, repo=repo, settings=orch.settings, session=session,
        user_text=user_text, on_text=on_text, on_document=_noop, on_notice=_noop,
        on_question=on_question,
    )


async def test_one_question_rendered_via_tool(orch, repo):
    s = await orch.start(1)
    claude = FakeClaude([Turn(text="Давай разберёмся.",
                              tool_calls=[("t1", "ask_question", {"question": "Кто страдает?"})])])
    txt, qs, on_text, on_question = _cbs()
    await _run(orch, repo, s, claude, on_text, on_question)
    assert qs == ["Кто страдает?"]        # criterion 2: exactly one question sent


async def test_ask_question_is_terminal(orch, repo):
    s = await orch.start(1)
    # model tries to ask AND immediately save in the same turn
    claude = FakeClaude([Turn(tool_calls=[
        ("t1", "ask_question", {"question": "Кто страдает?"}),
        ("t2", "save_artifact", {"step_id": "L1", "markdown": "# сам себе ответил"}),
    ])])
    txt, qs, on_text, on_question = _cbs()
    await _run(orch, repo, s, claude, on_text, on_question)
    assert qs == ["Кто страдает?"]
    arts = await repo.get_artifacts(s.id)
    assert "L1" not in arts               # criterion 12: save after ask is not executed
    assert s.current_step == "L1"


async def test_offtopic_spends_budget_and_lets_the_model_clarify(orch, repo):
    """CONTRACT CHANGE (fusion): the bot-echoes-on-offtopic mechanism is DELETED — it was a
    second source of truth next to the clarify budget. Offtopic now spends one delay and the
    model asks its own follow-up. The old expectation (bot parrots the stored question) is
    gone; the guarantee it stood for — the human is never stuck — is now structural and
    covered by tests/test_progress_invariant.py."""
    s = await orch.start(1)
    await orch.ask_question(s, "Кто страдает без продукта?")
    claude = FakeClaude([
        Turn(tool_calls=[("t1", "assess_answer", {"verdict": "offtopic"})]),
        Turn(tool_calls=[("t2", "ask_question", {"question": "Уточню: кто именно страдает?"})]),
    ])
    txt, qs, on_text, on_question = _cbs()
    await _run(orch, repo, s, claude, on_text, on_question, user_text="а сколько стоит?")
    assert qs == ["Уточню: кто именно страдает?"]  # the model clarifies, one question
    assert s.clarify_count == 1                     # one delay spent, budget is finite
    assert s.current_question == "Уточню: кто именно страдает?"


async def test_order_gate_requires_assess_first(orch, repo):
    s = await orch.start(1)
    await orch.ask_question(s, "Кто страдает?")
    # model ignores the open question and tries to save straight away
    claude = FakeClaude([
        Turn(tool_calls=[("t1", "save_artifact", {"step_id": "L1", "markdown": "# рано"})]),
        Turn(tool_calls=[("t2", "assess_answer", {"verdict": "answer"})]),
    ])
    txt, qs, on_text, on_question = _cbs()
    await _run(orch, repo, s, claude, on_text, on_question)
    arts = await repo.get_artifacts(s.id)
    assert "L1" not in arts               # criterion 6: not executed before assessment
    # the tool-loop deliberately gives the model further calls to act after assessing,
    # so the exact count is >=2 — what matters is that save never ran before assess
    assert claude.calls >= 2              # model was re-prompted


async def test_prose_dump_triggers_one_retry_then_fails_closed(orch, repo):
    s = await orch.start(1)
    dump = "Вопросы:\n1. Кто пользователь? Это бухгалтер?\n2. Какая боль? Что бесит?"
    claude = FakeClaude([Turn(text=dump), Turn(text=dump)])  # model repeats the violation
    txt, qs, on_text, on_question = _cbs()
    await _run(orch, repo, s, claude, on_text, on_question)
    assert claude.calls == 2                       # criterion 7: exactly one corrective retry
    assert dump not in txt                         # criterion 13: violating dump NOT sent
    assert len(qs) == 1 and qs[0].count("?") == 1  # fail-closed: only the first question sent
