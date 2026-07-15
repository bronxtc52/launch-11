"""Phase 3 — billing gate before Claude (criterion 5)."""
from launch11bot.app.turn import handle_incoming, handle_version_pick
from launch11bot.billing.service import BillingService
from launch11bot.llm.client import Turn


class FakeClaude:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def turn(self, system, history, version):
        self.calls += 1
        return self.script.pop(0) if self.script else Turn(text="")


async def _noop(*a):
    pass


async def test_needs_payment_blocks_claude(orch, repo):
    billing = BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")
    await billing.start_session(5, slug="a", version="lite")  # burn the free run
    await repo.delete_session(5)                              # abandon it
    fake = FakeClaude([Turn(text="should not run")])
    invoiced = []

    async def on_needs_payment():
        invoiced.append(1)

    res = await handle_incoming(
        user_id=5, text="моя идея", orch=orch, billing=billing, claude=fake, repo=repo,
        settings=orch.settings, on_text=_noop, on_document=_noop, on_notice=_noop,
        on_needs_payment=on_needs_payment, on_denied=_noop,
    )
    assert fake.calls == 0        # criterion 5: no Claude call when payment needed
    assert invoiced == [1]        # invoice offered
    assert res is None


async def test_free_run_proceeds_to_claude(orch, repo):
    billing = BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")
    fake = FakeClaude([Turn(text="привет, расскажи идею")])
    texts = []

    async def on_text(t):
        texts.append(t)

    await handle_incoming(
        user_id=6, text="идея портала", orch=orch, billing=billing, claude=fake, repo=repo,
        settings=orch.settings, on_text=on_text, on_document=_noop, on_notice=_noop,
        on_needs_payment=_noop, on_denied=_noop,
    )
    assert fake.calls == 1
    assert (await repo.get_billing(6))["free_used"] == 1


async def test_version_pick_grants_free_run(orch, repo):
    billing = BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")
    greeted = []

    async def on_greet(s):
        greeted.append(s)

    async def boom():
        raise AssertionError("should not need payment / already exist")

    await handle_version_pick(user_id=8, version="full", orch=orch, billing=billing,
                              on_greet=on_greet, on_needs_payment=boom, on_exists=boom)
    assert len(greeted) == 1
    assert greeted[0].version == "full" and greeted[0].current_step == "F1"
    assert (await repo.get_billing(8))["free_used"] == 1


async def test_version_pick_needs_payment_after_free_used(orch, repo):
    billing = BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")
    await billing.start_session(9, slug="a", version="lite")  # burn free run
    await repo.delete_session(9)
    invoiced = []

    async def on_needs_payment():
        invoiced.append(9)  # bot.py binds the invoice to this (clicking) user id

    async def boom(*a):
        raise AssertionError("unexpected")

    await handle_version_pick(user_id=9, version="full", orch=orch, billing=billing,
                              on_greet=boom, on_needs_payment=on_needs_payment, on_exists=boom)
    assert invoiced == [9]
    assert (await repo.get_billing(9))["free_used"] == 1  # no extra consume on a denied pick
