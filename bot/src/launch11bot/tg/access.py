"""Phase 1 access gate (council S2/PR1).

The bot is a public product but has no billing yet, so we allow only an
explicit allowlist of Telegram user IDs BEFORE any Claude call — this is the
Phase 1 cost guard. Removed/replaced by billing in Phase 3.
"""
from __future__ import annotations


def is_allowed(user_id: int, allowed_ids: set[int]) -> bool:
    return user_id in allowed_ids


def parse_allowed(csv: str) -> set[int]:
    out: set[int] = set()
    for chunk in (csv or "").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return out
