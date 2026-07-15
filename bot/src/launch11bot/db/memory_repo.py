"""In-memory Repo for hermetic tests. Emulates the same atomic contract as PgRepo."""
from __future__ import annotations

import asyncio

from ..pipeline import steps
from .repo import Session


class InMemoryRepo:
    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}          # id -> Session
        self._artifacts: dict[int, dict[str, str]] = {}   # session_id -> {step_id: md}
        self._messages: dict[int, list[tuple[str, str]]] = {}
        self._seq = 0
        self._lock = asyncio.Lock()

    def _active_for(self, tg_user_id: int) -> Session | None:
        for s in self._sessions.values():
            if s.tg_user_id == tg_user_id and s.status == "active":
                return s
        return None

    async def get_active_session(self, tg_user_id: int) -> Session | None:
        return self._active_for(tg_user_id)

    async def start_session(self, tg_user_id: int, slug: str, version: str) -> Session:
        async with self._lock:  # emulate the DB's single-active-session atomicity
            existing = self._active_for(tg_user_id)
            if existing:
                return existing
            self._seq += 1
            s = Session(self._seq, tg_user_id, slug, version,
                        current_step=steps.first_step_id(version), status="active")
            self._sessions[s.id] = s
            self._artifacts[s.id] = {}
            self._messages[s.id] = []
            return s

    async def save_artifact(self, session_id: int, step_id: str, markdown: str) -> None:
        self._artifacts.setdefault(session_id, {})[step_id] = markdown  # upsert

    async def get_artifacts(self, session_id: int) -> dict[str, str]:
        return dict(self._artifacts.get(session_id, {}))

    async def advance_step(self, session_id: int, from_step: str, to_step: str) -> bool:
        async with self._lock:
            s = self._sessions.get(session_id)
            if s is None or s.current_step != from_step:
                return False
            s.current_step = to_step
            return True

    async def set_status(self, session_id: int, status: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.status = status

    async def set_current_step(self, session_id: int, step_id: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.current_step = step_id

    async def add_message(self, session_id: int, role: str, text: str) -> None:
        self._messages.setdefault(session_id, []).append((role, text))

    async def get_messages(self, session_id: int, limit: int) -> list[tuple[str, str]]:
        return self._messages.get(session_id, [])[-limit:]

    async def delete_session(self, tg_user_id: int) -> None:
        for sid, s in list(self._sessions.items()):
            if s.tg_user_id == tg_user_id:
                self._sessions.pop(sid, None)
                self._artifacts.pop(sid, None)
                self._messages.pop(sid, None)
