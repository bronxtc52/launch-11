"""Repo protocol + Session model. Two implementations: InMemoryRepo, PgRepo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

FINISH_MARKER = "_finish"  # current_step value once all content steps are done


@dataclass
class Session:
    id: int
    tg_user_id: int
    slug: str
    version: str
    current_step: str
    status: str  # active | finished | aborted


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

    async def set_status(self, session_id: int, status: str) -> None: ...

    async def add_message(self, session_id: int, role: str, text: str) -> None: ...

    async def get_messages(self, session_id: int, limit: int) -> list[tuple[str, str]]: ...

    async def delete_session(self, tg_user_id: int) -> None: ...
