"""Transport-agnostic conversation turn service (testable without aiogram).

Handlers in tg/bot.py are thin adapters over these functions.
"""
from __future__ import annotations

import logging

from ..billing.service import NEEDS_PAYMENT
from ..llm.history import normalize_history
from ..llm.system_prompt import build_system
from ..pipeline.orchestrator import StepError
from ..pipeline.question import extract_first_question, validate_prose, validate_question
from ..pipeline.tool_dispatcher import dispatch

log = logging.getLogger(__name__)

MAX_TOOL_ITERS = 6

CONTRACT_CORRECTION = (
    "СТОП. Вопросы задаются ТОЛЬКО через ask_question, ровно по одному. НО контекст терять "
    "нельзя: ПЕРЕНЕСИ весь свой текст (формулировку, варианты, пояснение) в поле preamble "
    "вызова ask_question, а в question оставь ОДИН вопрос. Не выбрасывай содержание — "
    "человек должен видеть то, о чём его спрашивают."
)
FALLBACK_NUDGE = "Давай по порядку. Расскажи, пожалуйста, подробнее — с чего начнём?"
TRUNCATION_CORRECTION = (
    "Твой предыдущий ответ обрезало по лимиту токенов — человек его не увидит. Уложись "
    "короче: главное — тезисно, длинное содержимое сохраняй в артефакт через save_artifact, "
    "а человеку задай ОДИН вопрос через ask_question."
)
STRANDED_NUDGE = "Что скажешь — подтверждаешь, или что-то поправим?"
MOVING_ON = (
    "Понял, идём дальше — запишу по тому, что есть, и помечу как неполное. "
    "Захочешь вернуться и уточнить — просто скажи."
)


def _decision_hint(decision) -> str:
    """What the model must do next. The question is ALREADY closed by the controller —
    the model is told, not asked."""
    if decision.reason == "clarify_budget_exhausted":
        return (f"Лимит уточнений исчерпан — вопрос закрыт кодом (статус: {decision.status}). "
                f"Сохрани артефакт шага по тому, что есть, честно пометив неполноту. "
                f"Ответ человека дословно: «{decision.raw_answer}». Больше не переспрашивай.")
    if decision.reason == "deterministic_choice_match":
        return (f"Человек выбрал вариант «{decision.value}» — это ПОЛНОЦЕННЫЙ ответ, "
                f"засчитан кодом. Вопрос закрыт. Двигайся дальше.")
    if decision.reason == "user_said_unknown":
        return ("Человек честно сказал, что не знает — это нормальный исход. Вопрос закрыт "
                "(статус: unknown). Не дави, двигайся дальше.")
    return "Ответ принят, вопрос закрыт. Двигайся дальше."


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
    truncation_retry_left = 1
    asked_something = False
    # was the PREVIOUS reply already judged offtopic? then we're looping — break it out
    prev_verdict = session.last_verdict

    async def send_question(text: str):
        nonlocal asked_something
        asked_something = True
        """Every question the user sees MUST also land in the transcript — otherwise the
        next reply becomes a second consecutive `user` row, normalize_history coalesces
        them, and the model never learns it already re-asked (the endless-repeat loop)."""
        await on_question(text)
        assistant_texts.append(text)

    for _ in range(MAX_TOOL_ITERS):
        system = build_system(session, last_user_text=user_text)
        turn = await claude.turn(system, history, session.version)
        has_ask = any(n == "ask_question" for _, n, _ in turn.tool_calls)

        # A truncated answer is not an answer: max_tokens cut the model off mid-generation,
        # so it never reached its ask_question call. Forwarding the stump strands the human.
        if turn.stop_reason == "max_tokens":
            log.warning("model output truncated (max_tokens): %.60r", turn.text)
            if truncation_retry_left > 0:
                truncation_retry_left -= 1
                history.append({"role": "assistant", "content": turn.text or "(пусто)"})
                history.append({"role": "user", "content": TRUNCATION_CORRECTION})
                continue
            await send_question(FALLBACK_NUDGE)
            break

        # Inspect the WHOLE response before sending anything (council architect-2).
        # A violation is prose that carries a question or a list — checked mechanically
        # (unicode '？' normalized). Clean prose is legitimate and passes through, even
        # without a tool call: eating honest answers would be worse than the dump.
        violates = not has_ask and bool(turn.text) and validate_prose(turn.text) is not None
        if violates:
            log.info("contract violation: text=%.70r retry_left=%s", turn.text, contract_retry_left)
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
            # what the model actually decided — without this the dialogue is a black box
            log.info("tool=%s ok=%s verdict=%s missing=%r msg=%.60s",
                     name, res.ok, res.verdict, args.get("missing"), res.message)
            if name == "assess_answer" and res.ok:
                assessed = True
                # THE controller decides — the verdict is only its input. There is no
                # per-verdict branch here on purpose: a future verdict type spends the same
                # bounded budget and cannot open a new trap.
                decision = await orch.resolve_answer(session, user_text, verdict=res.verdict)
                log.info("controller: terminal=%s reason=%s status=%s clarify=%s/%s",
                         decision.terminal, decision.reason, decision.status,
                         session.clarify_count, session.clarify_budget)
                if decision.terminal:
                    if decision.reason == "clarify_budget_exhausted":
                        # code moves on and says so honestly — no pretending it was complete
                        await on_text(MOVING_ON)
                    res.message = _decision_hint(decision)
                else:
                    res.message = ("Нужно уточнение. Задай ОДИН уточняющий вопрос через "
                                   "ask_question — не повторяй прежний дословно.")
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

    # NEVER end a turn silently. One guard for every dead-end at once: model never called
    # assess_answer, validators rejected its question 6 times, MAX_TOOL_ITERS ran out, an
    # unknown verdict jammed the gate — previously each of these left the human staring at
    # nothing, forever, with no error either.
    if not assistant_texts:
        log.warning("silent turn averted: step=%s q=%r", session.current_step,
                    session.current_question)
        if session.current_question:
            await send_question(f"{OFFTOPIC_PREFIX}\n\n{session.current_question}")
        else:
            await send_question(FALLBACK_NUDGE)
    elif not asked_something and session.status == "active" and not session.current_question:
        # The bot spoke but asked nothing: the human is staring at a wall of text with no idea
        # what is wanted. Silence is not the only way to strand someone.
        log.warning("stranded user averted: spoke without asking, step=%s", session.current_step)
        await send_question(STRANDED_NUDGE)

    # Persist ONE assistant message for the whole turn so the stored transcript
    # stays strictly alternating user/assistant (review finding #1).
    if assistant_texts:
        await repo.add_message(session.id, "assistant", "\n\n".join(assistant_texts))
    return session
