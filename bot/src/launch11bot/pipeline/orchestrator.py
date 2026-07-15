"""Deterministic FSM over the Repo protocol.

Free-form dialogue happens in the LLM; structural transitions happen ONLY here,
so a chatty model can never skip a step or half-write the spec.
"""
from __future__ import annotations

from ..db.repo import FINISH_MARKER, Session
from . import assemble, steps


class StepError(Exception):
    """A pipeline transition was rejected (bad step, skip-ahead, incomplete finish)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Orchestrator:
    def __init__(self, repo, settings):
        self.repo = repo
        self.settings = settings

    async def start(self, tg_user_id: int, idea_slug: str | None = None) -> Session:
        slug = _slugify(idea_slug) if idea_slug else f"product-{tg_user_id}"
        return await self.repo.start_session(tg_user_id, slug, "lite")

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

        # persist (upsert — re-saving overwrites, never duplicates)
        await self.repo.save_artifact(session.id, step_id, markdown)

        # advance ONLY when the saved step is the current one; re-saving a past
        # step overwrites its artifact without moving the pointer.
        if idx == cur_idx:
            nxt = steps.next_step_id(version, step_id) or FINISH_MARKER
            if await self.repo.advance_step(session.id, step_id, nxt):
                session.current_step = nxt
        return session

    async def can_finish(self, session: Session) -> bool:
        arts = await self.repo.get_artifacts(session.id)
        return set(steps.step_ids(session.version)).issubset(arts.keys())

    async def finish(self, session: Session) -> str:
        if not await self.can_finish(session):
            raise StepError("пайплайн не завершён — не все шаги заполнены")
        arts = await self.repo.get_artifacts(session.id)
        spec = assemble.assemble_spec(session.slug, session.version, arts)
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


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
    return s[:40] or "product"
