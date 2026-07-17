"""Deterministic FSM over the Repo protocol.

Free-form dialogue happens in the LLM; structural transitions happen ONLY here,
so a chatty model can never skip a step or half-write the spec.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..db.repo import FINISH_MARKER, VERDICTS, Session
from . import assemble, steps
from .choice import is_dont_know, match_choice
from .question import validate_question
from .slug import slugify as _slugify


@dataclass
class Decision:
    """What the CODE decided about the human's reply. The model's verdict is an input to
    this, never the decision itself (fusion: 'модель может задерживать, но не останавливать')."""
    terminal: bool
    reason: str                    # deterministic_choice_match | llm_answer | user_said_unknown
                                   # | user_skip | clarify_budget_exhausted | need_clarify
    status: str | None = None      # complete | partial | offtopic | unknown | skipped
    raw_answer: str | None = None
    value: str | None = None       # the matched option for a closed choice


class StepError(Exception):
    """A pipeline transition was rejected (bad step, skip-ahead, incomplete finish)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Orchestrator:
    def __init__(self, repo, settings):
        self.repo = repo
        self.settings = settings

    async def start(self, tg_user_id: int, idea_slug: str | None = None,
                    version: str = "lite") -> Session:
        slug = _slugify(idea_slug) if idea_slug else f"product-{tg_user_id}"
        return await self.repo.start_session(tg_user_id, slug, version)

    async def resume(self, tg_user_id: int) -> Session | None:
        return await self.repo.get_active_session(tg_user_id)

    async def save_artifact(self, session: Session, step_id: str, markdown: str) -> Session:
        # The verdict no longer blocks: it lost that power (fusion C). Progress is gated by
        # the controller — a step may not be saved while a question is still open, and the
        # controller is what closes questions (always within a bounded number of delays).
        if session.current_question:
            raise StepError("сначала закрой открытый вопрос — оцени ответ человека")
        version = session.version
        idx = steps.step_index(version, step_id)
        if idx < 0:
            raise StepError(f"неизвестный шаг: {step_id}")
        if len(markdown.encode("utf-8")) > self.settings.max_artifact_bytes:
            raise StepError("артефакт слишком большой")

        cur_idx = steps.step_index(version, session.current_step)
        if cur_idx >= 0 and idx > cur_idx:
            raise StepError("нельзя перескочить вперёд через незавершённые шаги")

        # per-session size cap (council S3 / review #3)
        existing = await self.repo.get_artifacts(session.id)
        total = sum(len(v.encode("utf-8")) for k, v in existing.items() if k != step_id)
        if total + len(markdown.encode("utf-8")) > self.settings.max_session_artifact_bytes:
            raise StepError("суммарный размер артефактов сессии превышен")

        if idx == cur_idx:
            # advance ONLY when saving the current step — upsert + conditional
            # advance atomically in one transaction (plan A1/C1 / review #4).
            nxt = steps.next_step_id(version, step_id) or FINISH_MARKER
            if await self.repo.save_and_advance(session.id, step_id, markdown, step_id, nxt):
                session.current_step = nxt
        else:
            # re-saving a past step: overwrite its artifact, do not move the pointer
            await self.repo.save_artifact(session.id, step_id, markdown)
        return session

    async def set_product_name(self, session: Session, name: str) -> str:
        """The model names the product once it knows it. The filename the human receives
        depends on this, so junk is rejected rather than slugified into nonsense."""
        raw = (name or "").strip()
        if not raw or len(raw) > 120:
            raise StepError("название продукта: 2-6 слов, коротко и по делу")
        slug = _slugify(raw)
        if len(slug) < 3 or slug == "product":
            raise StepError(f"название «{raw}» не годится для имени файла — дай осмысленное")
        await self.repo.set_slug(session.id, slug)
        session.slug = slug
        return slug

    async def ask_question(self, session: Session, question: str,
                           options: list[str] | None = None) -> str:
        """Store the ONE open question. Content is validated mechanically — a multi-question
        dump must not sneak through inside the tool argument.

        NOTE: this deliberately does NOT reset clarify_count. Resetting the counter on every
        re-ask is exactly what made the delay-loop invisible and unbounded."""
        reason = validate_question(question)
        if reason:
            raise StepError(f"вопрос отклонён: {reason} — задай ровно один короткий вопрос")
        q = question.strip()
        await self.repo.set_question(session.id, q, options=options)
        session.current_question = q
        session.current_options = options
        return q

    async def assess_answer(self, session: Session, verdict: str, missing: str | None = None) -> str:
        """Record the model's opinion. It is an INPUT to the controller — it no longer decides
        anything by itself (the verdict lost its blocking power)."""
        if verdict not in VERDICTS:
            raise StepError(f"неизвестный вердикт: {verdict}")
        await self.repo.set_verdict(session.id, verdict)
        session.last_verdict = verdict
        return verdict

    async def resolve_answer(self, session: Session, user_text: str,
                             verdict: str | None = None) -> Decision:
        """THE controller. Code decides whether the step moves on; the model only delays.

        There is intentionally ONE branch for every non-`answer` verdict: a future verdict
        type spends the same budget and cannot open a new trap."""
        # 0. explicit human intent beats any model opinion
        if is_dont_know(user_text):
            return await self._close(session, "unknown", "user_said_unknown", user_text)

        # 1. a closed choice is judged by CODE — the model is not the judge here
        picked = match_choice(user_text, session.current_options)
        if picked is not None:
            return await self._close(session, "complete", "deterministic_choice_match",
                                     user_text, value=picked)

        # 2. the model considers the answer sufficient
        if verdict == "answer":
            return await self._close(session, "complete", "llm_answer", user_text)

        # 3. single branch for partial | offtopic | any future type
        if session.clarify_count < session.clarify_budget:
            session.clarify_count += 1
            await self.repo.set_clarify_count(session.id, session.clarify_count)
            return Decision(terminal=False, reason="need_clarify", raw_answer=user_text)

        # 4. budget exhausted -> code moves on, marking reality honestly
        status = verdict if verdict in ("partial", "offtopic") else "unknown"
        return await self._close(session, status, "clarify_budget_exhausted", user_text)

    async def _close(self, session: Session, status: str, reason: str,
                     raw: str, value: str | None = None) -> Decision:
        await self.repo.set_question(session.id, None, options=None)
        await self.repo.set_clarify_count(session.id, 0)
        session.current_question = None
        session.current_options = None
        session.clarify_count = 0
        return Decision(terminal=True, reason=reason, status=status, raw_answer=raw, value=value)

    async def skip_question(self, session: Session) -> Session:
        """User escape hatch (/skip): never trap a human inside a question."""
        await self._close(session, "skipped", "user_skip", "")
        await self.repo.set_verdict(session.id, None)
        session.last_verdict = None
        return session

    async def set_version(self, session: Session, version: str) -> Session:
        if version not in steps.PIPELINES:
            raise StepError(f"неизвестная версия: {version}")
        arts = await self.repo.get_artifacts(session.id)
        if arts:
            raise StepError("нельзя сменить версию — уже есть сохранённые артефакты")
        first = steps.first_step_id(version)
        await self.repo.set_version(session.id, version, first)
        session.version = version
        session.current_step = first
        return session

    async def create_adr(self, session: Session, title: str, markdown: str) -> int:
        if not title or not markdown:
            raise StepError("ADR требует title и markdown")
        if len(markdown.encode("utf-8")) > self.settings.max_artifact_bytes:
            raise StepError("ADR слишком большой")
        return await self.repo.create_adr(session.id, title, markdown)

    async def can_finish(self, session: Session) -> bool:
        arts = await self.repo.get_artifacts(session.id)
        return set(steps.step_ids(session.version)).issubset(arts.keys())

    async def finish(self, session: Session) -> str:
        """Assemble and deliver the spec. Status gates MONEY, not delivery.

        The old guard (`status == "finished"` -> StepError) made a failed delivery permanent:
        the status was committed BEFORE the document reached Telegram, so one flaky send left
        the human with no spec, no refund (reset only matches 'active') and a paywall on the
        next /start — the incident, moved 30 seconds to the right. Re-assembly is deterministic
        and the run is already paid for, so re-delivering is always safe.

        Order matters: can_finish -> assemble -> conditional close -> return. Closing first
        would mean a failed assemble leaves 'finished' with no spec and no way back.
        """
        if session.status == "abandoned":
            raise StepError("сессия брошена — начни заново через /start")
        if not await self.can_finish(session):
            raise StepError("пайплайн не завершён — не все шаги заполнены")
        arts = await self.repo.get_artifacts(session.id)
        adrs = await self.repo.get_adrs(session.id)
        spec = assemble.assemble_spec(session.slug, session.version, arts, adrs)
        if session.status != "finished":
            # False => the human abandoned it mid-turn: do NOT resurrect, do NOT deliver
            if not await self.repo.set_status_if_active(session.id, "finished"):
                raise StepError("сессия брошена — начни заново через /start")
            session.status = "finished"
        return spec

    async def progress(self, session: Session) -> dict:
        arts = await self.repo.get_artifacts(session.id)
        done = set(arts.keys())
        return {
            "version": session.version,
            "current_step": session.current_step,
            "steps": [
                {"id": s.id, "title": s.title, "done": s.id in done}
                for s in steps.PIPELINES[session.version]
            ],
        }
