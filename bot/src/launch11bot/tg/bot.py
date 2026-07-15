"""aiogram handlers — thin adapters over app.turn (gate -> orchestrator -> Claude)."""
from __future__ import annotations

import io
import logging

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..app.turn import handle_incoming
from ..db.repo import FINISH_MARKER
from ..llm.client import ClaudeClient
from ..pipeline.orchestrator import Orchestrator
from .access import is_allowed
from .keyboards import nav_keyboard, version_keyboard
from .sanitize import chunk_html, md_to_telegram_html

VERSION_NAMES = {"full": "Full (11 шагов)", "lite": "Lite", "spec_only": "Spec-only (техчасть)"}

log = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я проведу тебя по пайплайну запуска продукта Маргулана Сейсембая: "
    "от сырой идеи до готовой spec.md. На каждом шаге я задаю вопросы и помогаю "
    "сформулировать.\n\n"
    "Для начала выбери версию пайплайна — кнопкой ниже 👇"
)
DENIED = "Доступ ограничен на этапе бета-теста."


def build_dispatcher(settings, repo) -> Dispatcher:
    dp = Dispatcher()
    orch = Orchestrator(repo, settings)
    claude = ClaudeClient(settings)
    allowed = settings.allowed_user_ids

    async def send_html(msg: Message, text: str, keyboard: bool = True):
        for part in chunk_html(md_to_telegram_html(text)):
            await msg.answer(part, parse_mode="HTML",
                             reply_markup=nav_keyboard() if keyboard else None)

    async def send_spec(msg: Message, slug: str, spec: str):
        buf = io.BytesIO(spec.encode("utf-8"))
        await msg.answer_document(
            BufferedInputFile(buf.getvalue(), filename=f"{slug}-spec.md"),
            caption="Готово! Вот твоя spec.md 🎉",
        )

    @dp.message(Command("start"))
    async def on_start(msg: Message):
        if not is_allowed(msg.from_user.id, allowed):
            await msg.answer(DENIED)
            return
        existing = await orch.resume(msg.from_user.id)
        if existing and existing.current_step != FINISH_MARKER:
            await msg.answer(f"С возвращением! Ты на шаге {existing.current_step}. Продолжим.",
                             reply_markup=nav_keyboard())
        elif existing:
            await msg.answer("Все шаги пройдены — напиши что-нибудь, чтобы собрать spec.md, "
                             "или нажми «Начать заново».", reply_markup=nav_keyboard())
        else:
            await msg.answer(WELCOME, reply_markup=version_keyboard())

    @dp.callback_query(F.data.startswith("ver:"))
    async def on_pick_version(cq: CallbackQuery):
        if not is_allowed(cq.from_user.id, allowed):
            await cq.answer(DENIED)
            return
        version = cq.data.split(":", 1)[1]
        if version not in VERSION_NAMES:
            await cq.answer("Неизвестная версия")
            return
        existing = await orch.resume(cq.from_user.id)
        if existing:
            await cq.answer("У тебя уже есть активная сессия — /reset чтобы начать заново")
            return
        await orch.start(cq.from_user.id, version=version)
        await cq.message.answer(
            f"Версия: {VERSION_NAMES[version]}. Расскажи свою идею — с чего начнём?",
            reply_markup=nav_keyboard(),
        )
        await cq.answer()

    @dp.message(Command("reset"))
    async def on_reset(msg: Message):
        if not is_allowed(msg.from_user.id, allowed):
            await msg.answer(DENIED)
            return
        await repo.delete_session(msg.from_user.id)
        await msg.answer("Сессия удалена. Напиши /start, чтобы начать заново.")

    @dp.callback_query(F.data == "progress")
    async def on_progress(cq: CallbackQuery):
        if not is_allowed(cq.from_user.id, allowed):
            await cq.answer(DENIED)
            return
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
        if not is_allowed(cq.from_user.id, allowed):
            await cq.answer(DENIED)
            return
        await repo.delete_session(cq.from_user.id)
        await cq.message.answer("Сессия удалена. Напиши /start, чтобы начать заново.")
        await cq.answer()

    @dp.message(F.text)
    async def on_text(msg: Message):
        try:
            await handle_incoming(
                user_id=msg.from_user.id, text=msg.text, allowed=allowed,
                orch=orch, claude=claude, repo=repo, settings=settings,
                on_text=lambda t: send_html(msg, t),
                on_document=lambda slug, spec: send_spec(msg, slug, spec),
                on_notice=lambda m: msg.answer(m),
                on_denied=lambda: msg.answer(DENIED),
            )
        except Exception:
            log.exception("turn failed")
            await msg.answer("Упс, что-то сбойнуло на моей стороне. Попробуй ещё раз.")

    return dp
