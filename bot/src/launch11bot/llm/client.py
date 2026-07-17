"""Anthropic client wrapper: one dialogue turn with tool-use, deadline, backoff."""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from ..pipeline import steps
from . import tools

log = logging.getLogger(__name__)

# Grow the wait instead of hammering: the incident was a 7-minute 529 window, and the old loop
# burned all 3 attempts in ~5 seconds — useless against it, and it pounded an API that was
# explicitly asking us to back off.
BACKOFF_S = (1, 2, 4, 8, 16)   # 31s floor
JITTER = 0.25                  # spread only UPWARD: symmetric jitter could shrink the total
                               # to ~23s, making the "budget >= 30s" guarantee true only
                               # sometimes. Waiting a bit longer is free; under-waiting is the
                               # bug we are fixing.
MAX_SLEEP_S = 30.0             # hard cap on ANY single wait, deadline or not: a server-sent
                               # `Retry-After: 3600` would otherwise park the whole turn for an
                               # hour. Obeying a back-off request must not become a hang.


class ClaudeOverloaded(Exception):
    """Anthropic is overloaded/unreachable and the turn's budget ran out.

    Distinct from a generic failure so the human is told the truth («Claude перегружен»)
    instead of «сбойнуло на моей стороне» — it is not their fault and retrying instantly
    will not help.
    """


def _is_retryable(e: Exception) -> bool:
    """Retry what waiting can fix: overload, rate limit, any 5xx, timeouts, connection blips.

    NOT 4xx (except 429) — a bad request stays bad no matter how long we wait.
    Note: `asyncio.wait_for` raises asyncio.TimeoutError, NOT anthropic.APITimeoutError;
    the old bare `except Exception` retried it, so omitting it here would be a silent
    regression. Same for plain 5xx: we disable the SDK's own retries, so they are ours now.
    """
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return True
    code = getattr(e, "status_code", None)
    if code is not None:
        return code == 429 or 500 <= code < 600
    return type(e).__name__ in ("APITimeoutError", "APIConnectionError")


def _retry_after(e: Exception) -> float | None:
    """Honour the server's own back-off request when it sends one."""
    resp = getattr(e, "response", None)
    try:
        v = resp.headers.get("retry-after") if resp is not None else None
        return float(v) if v else None
    except (AttributeError, TypeError, ValueError):
        return None


@dataclass
class Turn:
    text: str = ""                                   # assistant prose to show the user
    stop_reason: str | None = None                   # "max_tokens" => the answer is CUT OFF
    tool_calls: list[tuple[str, str, dict]] = field(default_factory=list)  # (id, name, input)
    raw_assistant: list = field(default_factory=list)  # assistant content blocks (for tool loop)


class ClaudeClient:
    def __init__(self, settings):
        self.settings = settings
        # max_retries=0: the SDK's retries multiply with ours (3 of ours x 3 of its x 6 tool
        # iterations = ~90 requests for ONE user message). One retry layer, ours, is the truth.
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), max_retries=0)

    async def turn(self, system: str, history: list[dict], version: str,
                   *, deadline: float | None = None,
                   on_wait=None) -> Turn:
        """history: Anthropic-format messages. Returns assistant text + any tool calls.

        `deadline` is a monotonic timestamp bounding THIS WHOLE TURN, shared across the caller's
        tool loop — a per-call budget would multiply by the loop into minutes of silence.
        Checked before EVERY attempt (not just retries) and clamps each call's timeout;
        without the clamp the deadline is decoration.
        `on_wait` (optional) is called once, before the first sleep, so the human learns we are
        waiting rather than dead.
        """
        # keyword-only with a default: 10 test doubles implement turn(system, history, version)
        last_exc: Exception | None = None
        notified = False

        for i, base in enumerate((0.0,) + BACKOFF_S):
            remaining = None if deadline is None else deadline - asyncio.get_running_loop().time()
            if remaining is not None and remaining <= 0:
                raise ClaudeOverloaded("turn budget exhausted") from last_exc

            if i:  # not the first attempt -> wait first
                delay = base * (1 + random.uniform(0, JITTER))
                ra = _retry_after(last_exc) if last_exc else None
                if ra is not None:
                    delay = ra
                delay = min(delay, MAX_SLEEP_S)  # belt-and-braces: never hang on Retry-After
                if remaining is not None:
                    if delay >= remaining:
                        # obeying it would outlive the turn: don't hammer, don't fake waiting
                        raise ClaudeOverloaded("wait exceeds turn budget") from last_exc
                if on_wait and not notified:
                    notified = True
                    try:
                        await on_wait()
                    except Exception:  # a courtesy notice must never kill the turn
                        log.debug("on_wait notice failed", exc_info=True)
                await asyncio.sleep(delay)
                remaining = None if deadline is None else deadline - asyncio.get_running_loop().time()
                if remaining is not None and remaining <= 0:
                    raise ClaudeOverloaded("turn budget exhausted") from last_exc

            timeout = self.settings.claude_timeout_s
            if remaining is not None:
                timeout = min(timeout, remaining)
            try:
                resp = await asyncio.wait_for(
                    self._client.messages.create(
                        model=self.settings.launch11_model,
                        max_tokens=self.settings.claude_max_tokens,
                        system=system,
                        tools=tools.tool_defs(version),
                        messages=history,
                    ),
                    timeout=timeout,
                )
                out = Turn(raw_assistant=resp.content,
                           stop_reason=getattr(resp, 'stop_reason', None))
                for block in resp.content:
                    if block.type == "text":
                        out.text += block.text
                    elif block.type == "tool_use":
                        out.tool_calls.append((block.id, block.name, dict(block.input)))
                return out
            except Exception as e:
                if not _is_retryable(e):
                    raise  # waiting cannot fix it — surface immediately
                last_exc = e
                log.warning("claude attempt %d failed: %s", i + 1, type(e).__name__)

        raise ClaudeOverloaded("retries exhausted") from last_exc


def trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Sliding window (council P3): keep only the last N messages to bound context/cost."""
    return messages[-max_messages:] if len(messages) > max_messages else messages
