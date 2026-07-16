"""Transport-agnostic conversation turn service (testable without aiogram).

Handlers in tg/bot.py are thin adapters over these functions.
"""
from __future__ import annotations

from ..billing.service import NEEDS_PAYMENT
from ..llm.history import normalize_history
from ..llm.system_prompt import build_system
from ..pipeline.orchestrator import StepError
from ..pipeline.question import extract_first_question, validate_prose, validate_question
from ..pipeline.tool_dispatcher import dispatch

MAX_TOOL_ITERS = 6

CONTRACT_CORRECTION = (
    "СТОП. Ты нарушил контракт: вопросы задаются ТОЛЬКО через инструмент ask_question, "
    "ровно по одному, и никогда свободным текстом или списком. Переделай: вызови "
    "ask_question с ОДНИМ самым важным вопросом."
)
FALLBACK_NUDGE = "Давай по порядку. Расскажи, пожалуйста, подробнее — с чего начнём?"


async def handle_incoming(
    *, user_id, text, version, orch, billing, claude, repo, settings,
    on_text, on_document, on_notice, on_needs_payment, on_denied, on_question,
):
    """Two gates BEFORE any Claude call: optional beta allowlist, then billing
    entitlement. No entitlement → invoice, no session, no Claude (criterion 5).

    Entitlement is consumed here on the FIRST message (real work start), NOT on the
    version-pick click — clicking a version must never burn a free run (review architect-1)."""
    beta = getattr(settings, "beta_allowlist", set())
    if beta and user_id not in beta and not billing.is_owner(user_id):
        await on_denied()  # owners are never gated out
        return None
    session = await orch.resume(user_id)
    if session is None:
        # consume an entitlement atomically as the session is created
        result = await billing.start_session(user_id, slug=text, version=version)
        if result is NEEDS_PAYMENT:
            await on_needs_payment()
            return None
        session = result
    return await run_user_turn(
        orch=orch, claude=claude, repo=repo, settings=settings, session=session,
        user_text=text, on_text=on_text, on_document=on_document, on_notice=on_notice,
        on_question=on_question,
    )


async def _fail_closed(orch, session, text, on_question, on_text):
    """Model kept violating the contract: NEVER forward the dump. Salvage one question."""
    q = extract_first_question(text)
    if q and validate_question(q) is None:
        try:
            await on_question(await orch.ask_question(session, q))
            return
        except StepError:
            pass
    if session.current_question:
        await on_question(session.current_question)
    else:
        await on_text(FALLBACK_NUDGE)


async def run_user_turn(
    *, orch, claude, repo, settings, session, user_text,
    on_text, on_document, on_notice, on_question,
):
    await repo.add_message(session.id, "user", user_text)
    stored = await repo.get_messages(session.id, settings.max_context_messages)
    history = normalize_history(stored, settings.max_context_messages)

    assistant_texts: list[str] = []
    # assessment is owed only while a question is open
    assessed = session.current_question is None
    contract_retry_left = 1

    for _ in range(MAX_TOOL_ITERS):
        system = build_system(session)
        turn = await claude.turn(system, history, session.version)
        has_ask = any(n == "ask_question" for _, n, _ in turn.tool_calls)

        # Inspect the WHOLE response before sending anything (council architect-2).
        # A violation is prose that carries a question or a list — checked mechanically
        # (unicode '？' normalized). Clean prose is legitimate and passes through, even
        # without a tool call: eating honest answers would be worse than the dump.
        violates = not has_ask and bool(turn.text) and validate_prose(turn.text) is not None
        if violates:
            if contract_retry_left > 0:
                contract_retry_left -= 1
                history.append({"role": "assistant", "content": turn.text or "(пусто)"})
                history.append({"role": "user", "content": CONTRACT_CORRECTION})
                continue
            await _fail_closed(orch, session, turn.text, on_question, on_text)
            break

        # prose is forwarded only if it is mechanically clean (no question, no list) —
        # this also covers prose sent ALONGSIDE a tool call, where the dump used to slip
        # through in imperative form
        if turn.text and validate_prose(turn.text) is None:
            assistant_texts.append(turn.text)
            await on_text(turn.text)
        if not turn.tool_calls:
            break

        history.append({"role": "assistant", "content": turn.raw_assistant})
        results, stop = [], False
        for tool_id, name, args in turn.tool_calls:
            if not assessed and name != "assess_answer":
                # order-gate: judge the reply before doing anything else; NOT executed
                results.append({"type": "tool_result", "tool_use_id": tool_id,
                                "content": "Сначала вызови assess_answer для последней реплики "
                                           "пользователя, потом действуй."})
                continue
            res = await dispatch(orch, session, name, args)
            session = res.session
            if name == "assess_answer" and res.ok:
                assessed = True
                if res.verdict == "offtopic":
                    # the bot repeats the stored question verbatim — the model doesn't reword it
                    await on_question(session.current_question or FALLBACK_NUDGE)
                    stop = True
            if name == "ask_question" and res.ok and res.question:
                await on_question(res.question)
                assistant_texts.append(res.question)
                stop = True  # terminal: question asked, wait for the human
            if res.ok and name in ("save_artifact", "create_adr"):
                await on_notice(res.message)
            if res.spec:
                await on_document(session.slug, res.spec)
            results.append({"type": "tool_result", "tool_use_id": tool_id, "content": res.message})
            if stop:
                break
        history.append({"role": "user", "content": results})
        if stop:
            break

    # Persist ONE assistant message for the whole turn so the stored transcript
    # stays strictly alternating user/assistant (review finding #1).
    if assistant_texts:
        await repo.add_message(session.id, "assistant", "\n\n".join(assistant_texts))
    return session
