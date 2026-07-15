"""app.turn service — beta gate, billing gate, tool loop, history validity."""
from launch11bot.app.turn import handle_incoming
from launch11bot.billing.service import BillingService
from launch11bot.llm.client import Turn


class FakeClaude:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.last_history = None

    async def turn(self, system, history, version):
        self.calls += 1
        self.last_history = history
        return self.script.pop(0) if self.script else Turn(text="")


async def _noop(*a):
    pass


def _billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")


async def test_beta_allowlist_blocks_claude(orch, repo):
    orch.settings.beta_allowlist = {1}  # only user 1 allowed during beta
    fake = FakeClaude([Turn(text="should not run")])
    denied = []

    async def on_denied():
        denied.append(1)

    res = await handle_incoming(
        user_id=999, text="hi", version="lite", orch=orch, billing=_billing(repo), claude=fake, repo=repo,
        settings=orch.settings, on_text=_noop, on_document=_noop, on_notice=_noop,
        on_needs_payment=_noop, on_denied=on_denied,
    )
    assert fake.calls == 0
    assert denied == [1]
    assert res is None


async def test_full_loop_confirms_each_step_and_delivers_document(orch, repo):
    ids = ["L1", "L2", "L3", "L4"]
    script = [Turn(text=f"q{s}", tool_calls=[(f"t{s}", "save_artifact",
                                              {"step_id": s, "markdown": f"# {s}"})]) for s in ids]
    script.append(Turn(tool_calls=[("tf", "finish", {})]))
    script.append(Turn(text="готово"))
    fake = FakeClaude(script)
    notices, docs = [], []

    async def on_notice(m):
        notices.append(m)

    async def on_document(slug, spec):
        docs.append((slug, spec))

    await handle_incoming(
        user_id=7, text="партнёрский портал", version="lite", orch=orch, billing=_billing(repo), claude=fake,
        repo=repo, settings=orch.settings, on_text=_noop, on_document=on_document,
        on_notice=on_notice, on_needs_payment=_noop, on_denied=_noop,
    )
    assert len(notices) == 4
    assert len(docs) == 1
    slug, spec = docs[0]
    assert "портал" in slug
    assert "L4" in spec


async def test_history_passed_to_claude_is_valid(orch, repo):
    s = await orch.start(5, idea_slug="idea")
    for i in range(50):
        await repo.add_message(s.id, "user" if i % 2 == 0 else "assistant", f"m{i}")
    fake = FakeClaude([Turn(text="ok")])
    await handle_incoming(
        user_id=5, text="next", version="lite", orch=orch, billing=_billing(repo), claude=fake, repo=repo,
        settings=orch.settings, on_text=_noop, on_document=_noop, on_notice=_noop,
        on_needs_payment=_noop, on_denied=_noop,
    )
    h = fake.last_history
    assert h[0]["role"] == "user"
    roles = [m["role"] for m in h]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
