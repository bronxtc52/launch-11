"""Repro: the bot repeats its question verbatim while ignoring a valid answer.

Live evidence (session id=2): assistant asked "Какой фокус ближе — скорость, регулярность,
результат, или комбинация?", user replied "Скорость", verdict came back `offtopic` and the
bot echoed the question. The transcript showed TWO consecutive `user` rows (8, 9) — proof the
repeated question was never persisted.

See docs/specs/bug-answer-comprehension.md for the root-cause write-up.
"""
from launch11bot.app.turn import run_user_turn
from launch11bot.llm.client import Turn
from launch11bot.llm.system_prompt import build_system

QUESTION = "Какой фокус ближе — скорость, регулярность, результат, или комбинация?"


class FakeClaude:
    """Records what the model is actually shown, so we can assert it isn't lied to."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.systems: list[str] = []
        self.histories: list[list] = []

    async def turn(self, system, history, version):
        self.calls += 1
        self.systems.append(system)
        self.histories.append([dict(m) for m in history])
        return self.script.pop(0) if self.script else Turn(text="")


async def _noop(*a):
    pass


async def _run(orch, repo, session, claude, user_text, on_question=None, on_text=None):
    sent_q, sent_t = [], []

    async def _q(q):
        sent_q.append(q)

    async def _t(t):
        sent_t.append(t)

    await run_user_turn(
        orch=orch, claude=claude, repo=repo, settings=orch.settings, session=session,
        user_text=user_text, on_text=on_text or _t, on_document=_noop, on_notice=_noop,
        on_question=on_question or _q,
    )
    return sent_q, sent_t


# ---------------- RC2: the repeated question is never persisted -> the loop ----------------

async def test_turn_never_ends_silently_and_is_persisted(orch, repo):
    """CONTRACT CHANGE: the bot no longer echoes on offtopic (the controller's budget owns
    that now). But if the model then says nothing, the human must NOT get silence — and
    whatever is sent must still land in the transcript."""
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    claude = FakeClaude([Turn(tool_calls=[("t1", "assess_answer", {"verdict": "offtopic"})])])
    sent_q, _ = await _run(orch, repo, s, claude, "Скорость")

    assert sent_q, "bot must say something — a silent turn is a dead end"
    stored = await repo.get_messages(s.id, 40)
    assistant_rows = [t for r, t in stored if r == "assistant"]
    assert assistant_rows, "the re-asked question MUST be persisted, else the model never " \
                           "learns it already re-asked and loops forever"
    assert QUESTION in assistant_rows[-1]


async def test_no_two_consecutive_user_rows_after_a_repeat(orch, repo):
    """Exactly the live evidence: rows 8 and 9 were both `user` because the repeat vanished."""
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    await _run(orch, repo, s,
               FakeClaude([Turn(tool_calls=[("t1", "assess_answer", {"verdict": "offtopic"})])]),
               "Скорость")
    await _run(orch, repo, s,
               FakeClaude([Turn(tool_calls=[("t2", "assess_answer", {"verdict": "offtopic"})])]),
               "Я уже ответил выше")

    roles = [r for r, _ in await repo.get_messages(s.id, 40)]
    doubles = [i for i in range(len(roles) - 1) if roles[i] == roles[i + 1] == "user"]
    assert not doubles, f"two consecutive user rows at {doubles}: the bot's repeat was lost"


async def test_fail_closed_repeat_is_persisted(orch, repo):
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    # violates twice (list-like prose) AND has no salvageable question -> echoes current_question
    prose = "Давай так:\n1. расскажи про пользователя\n2. опиши боль"
    claude = FakeClaude([Turn(text=prose), Turn(text=prose)])
    sent_q, _ = await _run(orch, repo, s, claude, "Скорость")

    assert sent_q and QUESTION in sent_q[-1], "fail-closed falls back to the open question"
    stored = await repo.get_messages(s.id, 40)
    assert [t for r, t in stored if r == "assistant"], \
        "fail-closed re-ask must be persisted too"


# ---------------- RC1: the model is asked to judge a SERVICE message ----------------

async def test_order_gate_hint_carries_the_actual_user_reply(orch, repo):
    """The gate injects its hint as role=user, so it becomes the apparent 'last user reply'.
    The hint must therefore quote the human's real words and mark itself as service."""
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    claude = FakeClaude([
        Turn(tool_calls=[("t1", "ask_question", {"question": "Следующий вопрос?"})]),  # forgot assess
        Turn(tool_calls=[("t2", "assess_answer", {"verdict": "answer"})]),
    ])
    await _run(orch, repo, s, claude, "Скорость")

    assert claude.calls >= 2
    second_history = claude.histories[1]
    blob = str(second_history)
    assert "Скорость" in blob, "the model must still see the human's actual reply"
    hint = [m for m in second_history if m.get("role") == "user"][-1]
    assert "Скорость" in str(hint["content"]), \
        "the gate hint must quote the real reply — otherwise the model judges the service text"
    assert "служебн" in str(hint["content"]).lower(), \
        "the hint must mark itself as a service message, not a human turn"


# ---------------- RC3: no anchor for what is being judged ----------------

def test_system_prompt_anchors_the_open_question(orch):
    from launch11bot.db.repo import Session
    s = Session(1, 1, "slug", "lite", "L1", "active", current_question=QUESTION)
    system = build_system(s, last_user_text="Скорость")
    assert QUESTION in system, "the model must be told WHICH question is open"
    assert "Скорость" in system, "and WHICH human reply it must judge"


# ---------------- RC4/RC5: silent echo and the endless loop ----------------

async def test_offtopic_is_not_a_silent_verbatim_repeat(orch, repo):
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    claude = FakeClaude([Turn(tool_calls=[("t1", "assess_answer", {"verdict": "offtopic"})])])
    sent_q, _ = await _run(orch, repo, s, claude, "Скорость")

    msg = sent_q[-1]
    assert QUESTION in msg, "the question is still asked"
    assert msg.strip() != QUESTION, "but never as a bare, unexplained echo"


async def test_repeated_offtopic_is_bounded_by_the_budget(orch, repo):
    """CONTRACT CHANGE: the offtopic special case is deleted (fusion: one source of truth).
    Repeated offtopic now simply spends the shared clarify budget and the code moves on —
    which is a STRONGER guarantee than the old '/skip hint' and works for any verdict type."""
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    for i in range(6):
        await _run(orch, repo, s,
                   FakeClaude([Turn(tool_calls=[(f"t{i}", "assess_answer",
                                                 {"verdict": "offtopic"})])]),
                   "Я уже ответил выше")
        if s.current_question is None:
            break
    assert s.current_question is None, "budget must close the question — no endless loop"
    assert s.clarify_count <= s.clarify_budget


# ---------------- the happy path the user actually reported ----------------

async def test_short_valid_answer_is_accepted_and_not_repeated(orch, repo):
    s = await orch.start(1)
    await orch.ask_question(s, QUESTION)
    claude = FakeClaude([Turn(tool_calls=[
        ("t1", "assess_answer", {"verdict": "answer"}),
        ("t2", "ask_question", {"question": "Кто страдает без продукта?"}),
    ])])
    sent_q, _ = await _run(orch, repo, s, claude, "Скорость")

    assert QUESTION not in " ".join(sent_q), "a valid answer must NOT trigger a repeat"
    assert sent_q == ["Кто страдает без продукта?"]
    assert s.current_question == "Кто страдает без продукта?"
