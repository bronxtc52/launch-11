"""Deterministic closed-choice parsing.

The live bug: the bot offered three options, the human replied «Скорость», the model judged it
`partial`, and the bot re-asked forever. When a question offers a closed set of options, the
CODE decides whether the reply picks one — the LLM is not the judge (fusion: GPT-5.5 scenario 2).
"""
from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

# an explicit "I don't know" is a legitimate terminal outcome, not budget fuel
_DONT_KNOW = (
    "не знаю", "незнаю", "не в курсе", "хз", "понятия не имею", "затрудняюсь",
    "не могу сказать", "idk", "dunno", "no idea",
)


def _norm(text: str) -> str:
    return _PUNCT.sub(" ", (text or "").strip().lower()).strip()


def is_dont_know(text: str) -> bool:
    t = _norm(text)
    return any(t == p or t.startswith(p + " ") or t == p.replace(" ", "") for p in _DONT_KNOW)


def match_choice(text: str, options: list[str] | None) -> str | None:
    """Return the matched option, or None. Tolerant of case/whitespace/punctuation and of a
    reply that quotes the option inside a sentence («думаю, скорость»)."""
    if not options:
        return None
    t = _norm(text)
    if not t:
        return None
    for opt in options:
        o = _norm(opt)
        if not o:
            continue
        if t == o:
            return opt
        # whole-word occurrence: «скорость» inside «думаю скорость важнее»
        if re.search(rf"(?<!\w){re.escape(o)}(?!\w)", t):
            return opt
    return None
