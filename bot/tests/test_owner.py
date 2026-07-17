"""Owner exemption — unlimited runs, never billed, never beta-gated."""
from launch11bot.app.turn import handle_incoming
from launch11bot.billing.service import NEEDS_PAYMENT, BillingService
from launch11bot.llm.client import Turn

OWNER = 111  # synthetic id — real owner ids live only in Key Vault (launch11--*--OWNER-IDS)


class FakeClaude:
    def __init__(self):
        self.calls = 0

    async def turn(self, system, history, version, **_):
        self.calls += 1
        return Turn(text="ок")


async def _noop(*a):
    pass


def _billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон",
                          owners={OWNER})


async def test_owner_runs_are_never_billed(repo):
    billing = _billing(repo)
    # many runs in a row — never NEEDS_PAYMENT, counters untouched
    for i in range(5):
        s = await billing.start_session(OWNER, slug=f"идея-{i}", version="full")
        assert s is not NEEDS_PAYMENT
        await repo.abandon_session(OWNER)
    b = await repo.get_billing(OWNER)
    assert b["free_used"] == 0 and b["paid_credits"] == 0  # nothing consumed at all


async def test_non_owner_still_billed(repo):
    billing = _billing(repo)
    await billing.start_session(999, slug="идея", version="lite")
    await repo.set_status((await repo.get_active_session(999)).id, "finished")  # spent, not refunded
    assert await billing.start_session(999, slug="идея2", version="lite") is NEEDS_PAYMENT
    assert (await repo.get_billing(999))["free_used"] == 1


async def test_owner_bypasses_beta_gate(orch, repo):
    orch.settings.beta_allowlist = {12345}     # owner deliberately NOT in the allowlist
    claude = FakeClaude()
    denied = []

    async def on_denied():
        denied.append(1)

    await handle_incoming(
        user_id=OWNER, text="моя идея", version="full", orch=orch, billing=_billing(repo),
        claude=claude, repo=repo, settings=orch.settings, on_text=_noop, on_document=_noop,
        on_notice=_noop, on_question=_noop, on_needs_payment=_noop, on_denied=on_denied,
    )
    assert denied == []          # owner is never gated out
    assert claude.calls >= 1


async def test_owner_never_sees_invoice(orch, repo):
    billing = _billing(repo)
    await billing.start_session(OWNER, slug="a", version="lite")
    await repo.abandon_session(OWNER)
    invoiced = []

    async def on_needs_payment():
        invoiced.append(1)

    await handle_incoming(
        user_id=OWNER, text="ещё идея", version="lite", orch=orch, billing=billing,
        claude=FakeClaude(), repo=repo, settings=orch.settings, on_text=_noop,
        on_document=_noop, on_notice=_noop, on_question=_noop,
        on_needs_payment=on_needs_payment, on_denied=_noop,
    )
    assert invoiced == []        # no invoice for the owner, ever
