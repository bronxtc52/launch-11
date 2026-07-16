"""Deterministic question validation.

The whole point of Phase 4: enforcing the *channel* (ask_question) is not enough — the model
will happily put "1. … 2. … 3. …" INSIDE the tool argument and the dump just moves. So the
question TEXT is validated here, mechanically, before anything reaches the user.
"""
from __future__ import annotations

import re

MAX_QUESTION_LEN = 400

_LIST_MARKER = re.compile(r"(?m)^\s*(\d+[.)]|[-*•])\s+")
# a sentence that ends with '?' (kept non-greedy so we grab the FIRST one)
_FIRST_QUESTION = re.compile(r"([^.!?\n]{3,}\?)")


def validate_question(text: str | None) -> str | None:
    """Return a reason string if the question violates the one-question contract, else None."""
    if not text or not text.strip():
        return "пустой вопрос"
    t = text.strip()
    if len(t) > MAX_QUESTION_LEN:
        return f"вопрос длиннее {MAX_QUESTION_LEN} символов"
    if t.count("?") > 1:
        return "больше одного вопроса в сообщении"
    if _LIST_MARKER.search(t):
        return "список вопросов вместо одного"
    return None


def extract_first_question(text: str | None) -> str | None:
    """Fail-closed fallback: pull the FIRST single question out of a violating dump,
    so the user still gets a usable question instead of the wall of text."""
    if not text:
        return None
    m = _FIRST_QUESTION.search(text)
    if not m:
        return None
    q = re.sub(r"\s+", " ", m.group(1)).strip()
    q = re.sub(r"^(\d+[.)]|[-*•])\s*", "", q)          # drop a leading list marker
    q = re.sub(r"\*\*(.+?)\*\*", r"\1", q)             # drop markdown bold
    return q or None
