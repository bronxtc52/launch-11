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


OFFTOPIC_PREFIX = (
    "Вижу твой ответ, но он не отвечает на заданный вопрос. Переспрошу:"
)
STUCK_PREFIX = (
    "Похоже, я не могу понять твой ответ — это моя проблема, не твоя. "
    "Если вопрос лишний или непонятный, напиши /skip и пойдём дальше. Или ответь иначе:"
)


async def _fail_closed(orch, session, text, send_question, on_text):
    """Model kept violating the contract: NEVER forward the dump."""
    if session.current_question:
        # A question is already on the table — re-ask THAT one. Salvaging a question out of
        # the dump here would silently swap the wording the human is looking at.
        await send_question(f"{OFFTOPIC_PREFIX}\n\n{session.current_question}")
        return
    q = extract_first_question(text)  # nothing open: salvage one question from the dump
    if q and validate_question(q) is None:
        try:
            await send_question(await orch.ask_question(session, q))
            return
        except StepError:
            pass
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
    # was the PREVIOUS reply already judged offtopic? then we're looping — break it out
    prev_verdict = session.last_verdict

    async def send_question(text: str):
        """Every question the user sees MUST also land in the transcript — otherwise the
        next reply becomes a second consecutive `user` row, normalize_history coalesces
        them, and the model never learns it already re-asked (the endless-repeat loop)."""
        await on_question(text)
        assistant_texts.append(text)

    for _ in range(MAX_TOOL_ITERS):
        system = build_system(session, last_user_text=user_text)
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
            await _fail_closed(orch, session, turn.text, send_question, on_text)
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
                # Order-gate: judge the reply before doing anything else; NOT executed.
                # This hint is injected with role=user, so it LOOKS like the last human turn —
                # it must quote the real reply and mark itself as service, or the model judges
                # this very text and returns `offtopic` for a perfectly good answer.
                results.append({"type": "tool_result", "tool_use_id": tool_id,
                                "content": "[служебное сообщение системы, это НЕ реплика "
                                           f"человека] Сначала вызови assess_answer для реплики "
                                           f"человека: «{user_text}». Оценивай именно её."})
                continue
            res = await dispatch(orch, session, name, args)
            session = res.session
            if name == "assess_answer" and res.ok:
                assessed = True
                if res.verdict == "offtopic":
                    q = session.current_question
                    if not q:
                        await on_text(FALLBACK_NUDGE)
                    elif prev_verdict == "offtopic":
                        # second offtopic in a row on the same question: a wrong verdict must
                        # not trap a human who already answered — offer the way out
                        await send_question(f"{STUCK_PREFIX}\n\n{q}")
                    else:
                        # never a bare echo: say the answer was seen but didn't land
                        await send_question(f"{OFFTOPIC_PREFIX}\n\n{q}")
                    stop = True
            if name == "ask_question" and res.ok and res.question:
                await send_question(res.question)
            if res.ok and name in ("save_artifact", "create_adr"):
                await on_notice(res.message)
            if res.spec:
                await on_document(session.slug, res.spec)
            results.append({"type": "tool_result", "tool_use_id": tool_id, "content": res.message})
            if res.terminal:  # ask_question ends the turn — wait for the human
                stop = True
            if stop:
                skipped = turn.tool_calls[turn.tool_calls.index((tool_id, name, args)) + 1:]
                # every tool_use needs a tool_result or the next API call 400s
                results.extend({"type": "tool_result", "tool_use_id": tid,
                                "content": "пропущено: ход завершён"} for tid, _, _ in skipped)
                break
        history.append({"role": "user", "content": results})
        if stop:
            break

    # Persist ONE assistant message for the whole turn so the stored transcript
    # stays strictly alternating user/assistant (review finding #1).
    if assistant_texts:
        await repo.add_message(session.id, "assistant", "\n\n".join(assistant_texts))
    return session
