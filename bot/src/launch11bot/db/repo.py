"""Repo protocol + Session model. Two implementations: InMemoryRepo, PgRepo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

FINISH_MARKER = "_finish"  # current_step value once all content steps are done
VERDICTS = ("answer", "partial", "offtopic")


@dataclass
class Session:
    id: int
    tg_user_id: int
    slug: str
    version: str
    current_step: str
    status: str  # active | finished | aborted
    current_question: str | None = None  # the one open question, None when none is pending
    last_verdict: str | None = None      # answer | partial | offtopic


@runtime_checkable
class Repo(Protocol):
    async def get_active_session(self, tg_user_id: int) -> Session | None: ...

    async def start_session(self, tg_user_id: int, slug: str, version: str) -> Session:
        """Atomic: return the existing active session if one exists, else create one.
        Concurrent callers for the same user must converge on a single active session."""

    async def save_artifact(self, session_id: int, step_id: str, markdown: str) -> None:
        """Upsert (session_id, step_id) — re-saving a step overwrites, never duplicates."""

    async def get_artifacts(self, session_id: int) -> dict[str, str]: ...

    async def advance_step(self, session_id: int, from_step: str, to_step: str) -> bool:
        """Atomic conditional: set current_step=to_step only if it is currently from_step.
        Returns False if the session was not at from_step (lost race / already advanced)."""

    async def save_and_advance(
        self, session_id: int, step_id: str, markdown: str, from_step: str, to_step: str
    ) -> bool:
        """Upsert the artifact AND conditionally advance current_step in ONE transaction
        (plan A1/C1). Returns whether the pointer advanced."""

    async def set_status(self, session_id: int, status: str) -> None: ...

    async def set_version(self, session_id: int, version: str, first_step: str) -> None:
        """Change a session's pipeline version and reset current_step (empty session only)."""

    async def create_adr(self, session_id: int, title: str, markdown: str) -> int:
        """Append an ADR with the next sequential number; returns that number."""

    async def get_adrs(self, session_id: int) -> list[dict]:
        """ADRs for the session, ordered by number: [{n, title, markdown}]."""

    async def start_session_with_entitlement(
        self, tg_user_id: int, slug: str, version: str, free_runs: int
    ) -> Session | None:
        """Atomically: return the active session if one exists (NO consume); else consume one
        entitlement (free_used++ if free_used<free_runs, else paid_credits-- if >0) and create
        the session. Returns None if no entitlement (payment needed). Consumption is bound to
        session CREATION so a duplicate update / double-click consumes at most once."""

    async def grant_paid_credit(self, charge_id: str, tg_user_id: int, stars: int) -> bool:
        """Idempotent: insert the payment by charge_id; credit +1 only if newly inserted.
        Returns whether a credit was newly granted (False on duplicate charge_id)."""

    async def get_billing(self, tg_user_id: int) -> dict:
        """Read-only billing snapshot: {free_used, paid_credits}. For display, never a gate."""

    async def set_question(self, session_id: int, question: str | None) -> None:
        """Store (or clear) the single open question for this session."""

    async def set_verdict(self, session_id: int, verdict: str | None) -> None:
        """Store (or clear) the model's assessment of the last reply. Must be in VERDICTS."""

    async def add_message(self, session_id: int, role: str, text: str) -> None: ...

    async def get_messages(self, session_id: int, limit: int) -> list[tuple[str, str]]: ...

    async def delete_session(self, tg_user_id: int) -> None: ...
