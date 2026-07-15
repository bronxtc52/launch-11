"""aiogram handlers: wires access gate -> orchestrator -> Claude -> dispatcher -> Telegram."""
from __future__ import annotations

import io
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..llm.client import ClaudeClient, trim_history
from ..llm.system_prompt import build_system
from ..pipeline.orchestrator import Orchestrator
from ..pipeline.tool_dispatcher import dispatch
from .access import is_allowed
from .keyboards import nav_keyboard
from .sanitize import chunk_html, md_to_telegram_html

log = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я проведу тебя по пайплайну запуска продукта Маргулана Сейсембая: "
    "от сырой идеи до готовой spec.md. Пройдём несколько шагов (смысл → архитектура → задачи), "
    "на каждом я задаю вопросы и помогаю сформулировать.\n\n"
    "Расскажи свою идею своими словами — как другу. С чего хочешь начать?"
)


def build_dispatcher(settings, repo) -> Dispatcher:
    dp = Dispatcher()
    orch = Orchestrator(repo, settings)
    claude = ClaudeClient(settings)
    allowed = settings.allowed_user_ids

    async def send_html(msg: Message, text: str, keyboard=True):
        for part in chunk_html(md_to_telegram_html(text)):
            await msg.answer(part, parse_mode="HTML",
                             reply_markup=nav_keyboard() if keyboard else None)

    @dp.message(Command("start"))
    async def on_start(msg: Message):
        if not is_allowed(msg.from_user.id, allowed):  # gate BEFORE any Claude call
            await msg.answer("Доступ ограничен на этапе бета-теста.")
            return
        existing = await orch.resume(msg.from_user.id)
        if existing:
            prog = await orch.progress(existing)
            await msg.answer(f"С возвращением! Ты на шаге {prog['current_step']}. Продолжим.",
                             reply_markup=nav_keyboard())
        else:
            await orch.start(msg.from_user.id)
            await msg.answer(WELCOME, reply_markup=nav_keyboard())

    @dp.message(Command("reset"))
    async def on_reset(msg: Message):
        if not is_allowed(msg.from_user.id, allowed):
            return
        await repo.delete_session(msg.from_user.id)
        await msg.answer("Сессия удалена. Напиши /start, чтобы начать заново.")

    @dp.callback_query(F.data == "progress")
    async def on_progress(cq: CallbackQuery):
        session = await orch.resume(cq.from_user.id)
        if not session:
            await cq.answer("Нет активной сессии — /start")
            return
        prog = await orch.progress(session)
        lines = [f"{'✅' if s['done'] else '⬜'} {s['id']}: {s['title']}" for s in prog["steps"]]
        await cq.message.answer("Прогресс:\n" + "\n".join(lines))
        await cq.answer()

    @dp.callback_query(F.data == "reset")
    async def on_reset_cb(cq: CallbackQuery):
        await repo.delete_session(cq.from_user.id)
        await cq.message.answer("Сессия удалена. Напиши /start, чтобы начать заново.")
        await cq.answer()

    @dp.message(F.text)
    async def on_text(msg: Message):
        if not is_allowed(msg.from_user.id, allowed):  # gate BEFORE any Claude call
            await msg.answer("Доступ ограничен на этапе бета-теста.")
            return
        session = await orch.resume(msg.from_user.id)
        if not session:
            session = await orch.start(msg.from_user.id)

        await repo.add_message(session.id, "user", msg.text)
        stored = await repo.get_messages(session.id, settings.max_context_messages)
        history = trim_history(
            [{"role": r, "content": t} for r, t in stored], settings.max_context_messages
        )

        try:
            # intra-turn tool loop
            for _ in range(6):
                system = build_system(session)
                turn = await claude.turn(system, history, session.version)
                if turn.text:
                    await repo.add_message(session.id, "assistant", turn.text)
                    await send_html(msg, turn.text)
                if not turn.tool_calls:
                    break
                history.append({"role": "assistant", "content": turn.raw_assistant})
                results = []
                for tool_id, name, args in turn.tool_calls:
                    res = await dispatch(orch, session, name, args)
                    session = res.session
                    if res.spec:  # finish() succeeded -> deliver the document
                        await _send_spec(msg, session.slug, res.spec)
                    results.append({"type": "tool_result", "tool_use_id": tool_id,
                                    "content": res.message})
                history.append({"role": "user", "content": results})
        except Exception as e:
            log.exception("turn failed")
            await msg.answer("Упс, что-то сбойнуло на моей стороне. Попробуй ещё раз.")

    async def _send_spec(msg: Message, slug: str, spec: str):
        buf = io.BytesIO(spec.encode("utf-8"))
        await msg.answer_document(
            BufferedInputFile(buf.getvalue(), filename=f"{slug}-spec.md"),
            caption="Готово! Вот твоя spec.md 🎉",
        )

    return dp
