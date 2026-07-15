"""Deterministic FSM over the Repo protocol.

Free-form dialogue happens in the LLM; structural transitions happen ONLY here,
so a chatty model can never skip a step or half-write the spec.
"""
from __future__ import annotations

from ..db.repo import FINISH_MARKER, Session
from . import assemble, steps
from .slug import slugify as _slugify


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
        if session.status == "finished":
            raise StepError("сессия уже завершена")  # guard double delivery (review #9)
        if not await self.can_finish(session):
            raise StepError("пайплайн не завершён — не все шаги заполнены")
        arts = await self.repo.get_artifacts(session.id)
        adrs = await self.repo.get_adrs(session.id)
        spec = assemble.assemble_spec(session.slug, session.version, arts, adrs)
        await self.repo.set_status(session.id, "finished")
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
