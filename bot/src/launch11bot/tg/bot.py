"""aiogram handlers — thin adapters over app.turn + billing (Telegram Stars)."""
from __future__ import annotations

import io
import logging

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (BufferedInputFile, CallbackQuery, Message, PreCheckoutQuery)

from ..app.turn import handle_incoming
from ..billing.service import BillingService
from ..db.repo import FINISH_MARKER
from ..llm.client import ClaudeClient, ClaudeOverloaded
from ..pipeline.orchestrator import Orchestrator
from .keyboards import version_keyboard
from .sanitize import chunk_html, md_to_telegram_html

log = logging.getLogger(__name__)

VERSION_NAMES = {"full": "Full (11 шагов)", "lite": "Lite", "spec_only": "Spec-only (техчасть)"}
WELCOME = (
    "Привет! Я проведу тебя по пайплайну запуска продукта Маргулана Сейсембая: "
    "от сырой идеи до готовой spec.md. На каждом шаге я задаю вопросы и помогаю "
    "сформулировать.\n\nПервый прогон бесплатный. Выбери версию пайплайна 👇"
)
DENIED = "Доступ ограничен на этапе бета-теста."


def build_dispatcher(settings, repo) -> Dispatcher:
    dp = Dispatcher()
    orch = Orchestrator(repo, settings)
    claude = ClaudeClient(settings)
    billing = BillingService(repo, settings.free_runs, settings.stars_price, settings.stars_label,
                             owners=settings.owners)
    beta = settings.beta_allowlist
    pending_version: dict[int, str] = {}  # user_id -> chosen version, until first message

    def gated_out(user_id: int) -> bool:
        if billing.is_owner(user_id):
            return False  # owners always pass
        return bool(beta) and user_id not in beta

    async def send_html(msg: Message, text: str, keyboard: bool = False):
        # nav lives in the command menu (/progress, /reset) — an inline keyboard under every
        # single message was noise in a dialogue that is almost entirely questions
        for part in chunk_html(md_to_telegram_html(text)):
            await msg.answer(part, parse_mode="HTML")

    async def send_spec(msg: Message, slug: str, spec: str):
        buf = io.BytesIO(spec.encode("utf-8"))
        await msg.answer_document(
            BufferedInputFile(buf.getvalue(), filename=f"{slug}-spec.md"),
            caption="Готово! Вот твоя spec.md 🎉")

    async def send_invoice(user_id: int, chat_msg: Message):
        # user_id MUST be the paying user (never a message author — cq.message is authored
        # by the bot), so the invoice payload binds to them and crediting succeeds.
        await chat_msg.answer(
            "Бесплатный прогон использован. Чтобы начать новый — оплати звёздами Telegram:")
        await chat_msg.answer_invoice(**billing.invoice_params(user_id))

    async def _progress_text(user_id: int) -> str | None:
        session = await orch.resume(user_id)
        if not session:
            return None
        prog = await orch.progress(session)
        lines = [f"{'✅' if s_['done'] else '⬜'} {s_['id']}: {s_['title']}" for s_ in prog["steps"]]
        return "Прогресс:\n" + "\n".join(lines)

    @dp.message(Command("spec"))
    async def on_spec_cmd(msg: Message):
        """Re-deliver the spec of the last finished run.

        The escape hatch for a failed document send (Telegram blip, flood-control, a 200 KB
        file): the status commits before the document lands, so without this the human is left
        with no spec, no refund and a paywall — the incident, 30 seconds later. Re-assembly is
        deterministic and the run is already paid for, so this is safe to repeat.
        """
        if gated_out(msg.from_user.id):
            await msg.answer(DENIED)
            return
        session = await repo.get_last_finished_session(msg.from_user.id)
        if not session:
            await msg.answer("Готовой спеки пока нет — заверши прогон или начни: /start")
            return
        spec = await orch.finish(session)  # idempotent: re-assembles, does not re-charge
        await send_spec(msg, session.slug, spec)

    @dp.message(Command("progress"))
    async def on_progress_cmd(msg: Message):
        if gated_out(msg.from_user.id):
            await msg.answer(DENIED)
            return
        text = await _progress_text(msg.from_user.id)
        await msg.answer(text or "Нет активной сессии — /start")

    @dp.message(Command("start"))
    async def on_start(msg: Message):
        if gated_out(msg.from_user.id):
            await msg.answer(DENIED)
            return
        existing = await orch.resume(msg.from_user.id)
        if existing and existing.current_step != FINISH_MARKER:
            await msg.answer(f"С возвращением! Ты на шаге {existing.current_step}. Продолжим.")
            if existing.current_question:
                # coming back a day later: show the question that is still open, don't
                # leave the human guessing what the bot is waiting for
                await send_html(msg, f"Открытый вопрос:\n\n{existing.current_question}",
                                keyboard=False)
        elif existing:
            await msg.answer("Все шаги пройдены — напиши что-нибудь, чтобы собрать spec.md, "
                             "или начни заново: /reset")
        else:
            await msg.answer(WELCOME, reply_markup=version_keyboard())

    @dp.callback_query(F.data.startswith("ver:"))
    async def on_pick_version(cq: CallbackQuery):
        if gated_out(cq.from_user.id):
            await cq.answer(DENIED)
            return
        version = cq.data.split(":", 1)[1]
        if version not in VERSION_NAMES:
            await cq.answer("Неизвестная версия")
            return
        if await orch.resume(cq.from_user.id):
            await cq.answer("У тебя уже есть активная сессия — /reset чтобы начать заново")
            return
        # Just record the choice — NO billing here. The free run is consumed on the first
        # actual message, so clicking a version never burns an entitlement (review architect-1).
        pending_version[cq.from_user.id] = version
        await cq.message.answer(
            f"Версия: {VERSION_NAMES[version]}. Расскажи свою идею — с чего начнём?")
        await cq.answer()

    async def _do_reset(user_id: int, answer):
        """Abandon the run, give the entitlement back, and say what actually happened.

        «Сессия удалена» was a lie twice over: the session survives (it is the ledger) and,
        worse, it hid the refund — the whole point of the fix. Offer the version keyboard
        instead of letting the next stray text start a run on the default version.
        """
        refunded = await repo.abandon_session(user_id)
        pending_version.pop(user_id, None)
        if refunded:
            await answer("Начали заново — прогон вернулся на счёт. Выбери версию:",
                         reply_markup=version_keyboard())
        else:
            await answer("Начали заново. Выбери версию:", reply_markup=version_keyboard())

    @dp.message(Command("reset"))
    async def on_reset(msg: Message):
        if gated_out(msg.from_user.id):
            await msg.answer(DENIED)
            return
        await _do_reset(msg.from_user.id, msg.answer)

    @dp.message(Command("skip"))
    async def on_skip(msg: Message):
        # escape hatch: never trap a human inside an open question (council product_risk-5)
        if gated_out(msg.from_user.id):
            await msg.answer(DENIED)
            return
        session = await orch.resume(msg.from_user.id)
        if not session:
            await msg.answer("Нет активной сессии — /start")
            return
        await orch.skip_question(session)
        await msg.answer("Ок, пропускаем этот вопрос. Продолжай своими словами.")

    @dp.callback_query(F.data == "progress")
    async def on_progress(cq: CallbackQuery):
        if gated_out(cq.from_user.id):
            await cq.answer(DENIED)
            return
        text = await _progress_text(cq.from_user.id)   # old buttons in chat history keep working
        await cq.message.answer(text or "Нет активной сессии — /start")
        await cq.answer()

    @dp.callback_query(F.data == "reset")
    async def on_reset_cb(cq: CallbackQuery):
        if gated_out(cq.from_user.id):
            await cq.answer(DENIED)
            return
        # cq.from_user is the human; cq.message.from_user would be the BOT (billing bug, review)
        await _do_reset(cq.from_user.id, cq.message.answer)
        await cq.answer()

    @dp.pre_checkout_query()
    async def on_pre_checkout(pcq: PreCheckoutQuery):
        # fail-closed BEFORE the user is charged: validate currency/amount/payload-binding
        ok = billing.validate_payment(pcq.from_user.id, pcq.currency, pcq.total_amount,
                                      pcq.invoice_payload)
        await pcq.answer(ok=ok, error_message=None if ok else "Некорректный платёж")

    @dp.message(F.successful_payment)
    async def on_paid(msg: Message):
        sp = msg.successful_payment
        granted = await billing.on_successful_payment(
            msg.from_user.id, charge_id=sp.telegram_payment_charge_id,
            currency=sp.currency, total_amount=sp.total_amount, invoice_payload=sp.invoice_payload)
        if granted:
            await msg.answer("Оплата получена — доступен ещё один прогон! Напиши /start 🚀")
        else:
            await msg.answer("Платёж обработан.")  # duplicate/invalid — never double-credited

    @dp.message(F.text)
    async def on_text(msg: Message):
        try:
            version = pending_version.pop(msg.from_user.id, "lite")
            await handle_incoming(
                user_id=msg.from_user.id, text=msg.text, version=version, orch=orch,
                billing=billing, claude=claude, repo=repo, settings=settings,
                on_text=lambda t: send_html(msg, t),
                on_document=lambda slug, spec: send_spec(msg, slug, spec),
                on_notice=lambda m: msg.answer(m),
                # keep the nav buttons reachable: the dialogue is now almost entirely
                # questions, so keyboard=False here hid Прогресс/Заново forever
                on_question=lambda q: send_html(msg, q),
                on_needs_payment=lambda: send_invoice(msg.from_user.id, msg),
                on_denied=lambda: msg.answer(DENIED),
            )
        except ClaudeOverloaded:
            # log.error, NOT warning: sentry_sdk.init has no LoggingIntegration, so the default
            # event_level=ERROR means a warning would be a breadcrumb, not an issue — we'd go
            # blind on exactly the class of incident this handler exists for.
            log.error("anthropic overloaded — turn abandoned", exc_info=True)
            await msg.answer(
                "Claude сейчас перегружен — это на моей стороне, не у тебя. "
                "Твой ответ я сохранил: напиши «продолжай» через пару минут.")
        except Exception:
            log.exception("turn failed")
            await msg.answer("Упс, что-то сбойнуло на моей стороне. Попробуй ещё раз.")

    return dp
