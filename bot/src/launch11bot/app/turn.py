"""Transport-agnostic conversation turn service (testable without aiogram).

Handlers in tg/bot.py are thin adapters over these functions.
"""
from __future__ import annotations

from ..billing.service import NEEDS_PAYMENT
from ..llm.history import normalize_history
from ..llm.system_prompt import build_system
from ..pipeline.tool_dispatcher import dispatch

MAX_TOOL_ITERS = 6


async def handle_incoming(
    *, user_id, text, orch, billing, claude, repo, settings,
    on_text, on_document, on_notice, on_needs_payment, on_denied,
):
    """Two gates BEFORE any Claude call: optional beta allowlist, then billing
    entitlement. No entitlement → invoice, no session, no Claude (criterion 5)."""
    beta = getattr(settings, "beta_allowlist", set())
    if beta and user_id not in beta:
        await on_denied()
        return None
    session = await orch.resume(user_id)
    if session is None:
        # consume an entitlement atomically as the session is created
        result = await billing.start_session(user_id, slug=text, version="lite")
        if result is NEEDS_PAYMENT:
            await on_needs_payment()
            return None
        session = result
    return await run_user_turn(
        orch=orch, claude=claude, repo=repo, settings=settings, session=session,
        user_text=text, on_text=on_text, on_document=on_document, on_notice=on_notice,
    )


async def handle_version_pick(
    *, user_id, version, orch, billing, on_greet, on_needs_payment, on_exists,
):
    """Button path: create a session for the chosen version through the billing gate.
    Uses the CLICKING user's id (never a message author) so the invoice payload binds
    to the right user (regression guard for the on_pick_version invoice bug)."""
    if await orch.resume(user_id):
        await on_exists()
        return None
    result = await billing.start_session(user_id, slug=f"product-{user_id}", version=version)
    if result is NEEDS_PAYMENT:
        await on_needs_payment()
        return None
    await on_greet(result)
    return result


async def run_user_turn(
    *, orch, claude, repo, settings, session, user_text,
    on_text, on_document, on_notice,
):
    await repo.add_message(session.id, "user", user_text)
    stored = await repo.get_messages(session.id, settings.max_context_messages)
    history = normalize_history(stored, settings.max_context_messages)

    assistant_texts: list[str] = []
    for _ in range(MAX_TOOL_ITERS):
        system = build_system(session)
        turn = await claude.turn(system, history, session.version)
        if turn.text:
            assistant_texts.append(turn.text)
            await on_text(turn.text)
        if not turn.tool_calls:
            break
        history.append({"role": "assistant", "content": turn.raw_assistant})
        results = []
        for tool_id, name, args in turn.tool_calls:
            res = await dispatch(orch, session, name, args)
            session = res.session
            if res.ok and name in ("save_artifact", "create_adr"):
                await on_notice(res.message)  # deterministic "✅ …" surfaced to the user
            if res.spec:
                await on_document(session.slug, res.spec)
            results.append({"type": "tool_result", "tool_use_id": tool_id, "content": res.message})
        history.append({"role": "user", "content": results})

    # Persist ONE assistant message for the whole turn so the stored transcript
    # stays strictly alternating user/assistant (review finding #1).
    if assistant_texts:
        await repo.add_message(session.id, "assistant", "\n\n".join(assistant_texts))
    return session
