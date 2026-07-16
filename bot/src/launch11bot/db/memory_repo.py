"""In-memory Repo for hermetic tests. Emulates the same atomic contract as PgRepo."""
from __future__ import annotations

import asyncio

from ..pipeline import steps
from .repo import VERDICTS, Session


class InMemoryRepo:
    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}          # id -> Session
        self._artifacts: dict[int, dict[str, str]] = {}   # session_id -> {step_id: md}
        self._messages: dict[int, list[tuple[str, str]]] = {}
        self._adrs: dict[int, list[dict]] = {}
        self._billing: dict[int, dict] = {}       # tg_user_id -> {free_used, paid_credits}
        self._payments: dict[str, dict] = {}      # charge_id -> {...}
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

    async def save_and_advance(self, session_id, step_id, markdown, from_step, to_step) -> bool:
        async with self._lock:  # emulate PgRepo's single-transaction semantics
            self._artifacts.setdefault(session_id, {})[step_id] = markdown
            s = self._sessions.get(session_id)
            if s is None or s.current_step != from_step:
                return False
            s.current_step = to_step
            return True

    async def set_status(self, session_id: int, status: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.status = status

    async def set_version(self, session_id: int, version: str, first_step: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.version = version
            s.current_step = first_step

    async def create_adr(self, session_id: int, title: str, markdown: str) -> int:
        async with self._lock:
            lst = self._adrs.setdefault(session_id, [])
            n = len(lst) + 1
            lst.append({"n": n, "title": title, "markdown": markdown})
            return n

    async def get_adrs(self, session_id: int) -> list[dict]:
        return [dict(a) for a in self._adrs.get(session_id, [])]

    async def start_session_with_entitlement(self, tg_user_id, slug, version, free_runs):
        async with self._lock:  # emulate the single-transaction consume+create of PgRepo
            existing = self._active_for(tg_user_id)
            if existing:
                return existing  # no consume on resume
            b = self._billing.setdefault(tg_user_id, {"free_used": 0, "paid_credits": 0})
            if b["free_used"] < free_runs:
                b["free_used"] += 1
            elif b["paid_credits"] > 0:
                b["paid_credits"] -= 1
            else:
                return None  # needs payment — no session created
            self._seq += 1
            s = Session(self._seq, tg_user_id, slug, version,
                        current_step=steps.first_step_id(version), status="active")
            self._sessions[s.id] = s
            self._artifacts[s.id] = {}
            self._messages[s.id] = []
            return s

    async def grant_paid_credit(self, charge_id, tg_user_id, stars) -> bool:
        async with self._lock:
            if charge_id in self._payments:
                return False  # duplicate charge — no double credit
            self._payments[charge_id] = {"tg_user_id": tg_user_id, "stars": stars}
            b = self._billing.setdefault(tg_user_id, {"free_used": 0, "paid_credits": 0})
            b["paid_credits"] += 1
            return True

    async def get_billing(self, tg_user_id) -> dict:
        return dict(self._billing.get(tg_user_id, {"free_used": 0, "paid_credits": 0}))

    async def set_question(self, session_id: int, question: str | None) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.current_question = question

    async def set_verdict(self, session_id: int, verdict: str | None) -> None:
        if verdict is not None and verdict not in VERDICTS:
            raise ValueError(f"bad verdict: {verdict}")  # mirrors the DB CHECK constraint
        s = self._sessions.get(session_id)
        if s:
            s.last_verdict = verdict

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
                self._adrs.pop(sid, None)
