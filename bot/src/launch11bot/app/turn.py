"""Transport-agnostic conversation turn service (testable without aiogram).

Handlers in tg/bot.py are thin adapters over these functions.
"""
from __future__ import annotations

from ..llm.history import normalize_history
from ..llm.system_prompt import build_system
from ..pipeline.tool_dispatcher import dispatch
from ..tg.access import is_allowed

MAX_TOOL_ITERS = 6


async def handle_incoming(
    *, user_id, text, allowed, orch, claude, repo, settings,
    on_text, on_document, on_notice, on_denied,
):
    """Gate FIRST (Claude must not be called for denied users — criterion 9),
    then run the dialogue turn."""
    if not is_allowed(user_id, allowed):
        await on_denied()
        return None
    session = await orch.resume(user_id)
    if session is None:
        session = await orch.start(user_id, idea_slug=text)  # slug from the user's idea
    return await run_user_turn(
        orch=orch, claude=claude, repo=repo, settings=settings, session=session,
        user_text=text, on_text=on_text, on_document=on_document, on_notice=on_notice,
    )


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
