"""Build a valid Anthropic message history from a stored transcript.

Anthropic requires: first message role=user, and no two same-role messages in a
row is strongly preferred. Naive windowing (messages[-N:]) can start with an
assistant turn and break the API on long dialogues (review finding #1).
"""
from __future__ import annotations


def normalize_history(messages: list[tuple[str, str]], max_messages: int) -> list[dict]:
    # 1. coalesce consecutive same-role turns into one
    coalesced: list[tuple[str, str]] = []
    for role, text in messages:
        if coalesced and coalesced[-1][0] == role:
            coalesced[-1] = (role, coalesced[-1][1] + "\n\n" + text)
        else:
            coalesced.append((role, text))

    # 2. keep only the last N
    window = coalesced[-max_messages:] if len(coalesced) > max_messages else coalesced

    # 3. drop leading assistant turns so the history starts with a user message
    while window and window[0][0] != "user":
        window.pop(0)

    return [{"role": r, "content": t} for r, t in window]
