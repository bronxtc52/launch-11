"""Anthropic client wrapper: one dialogue turn with tool-use, timeout, retry cap."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from ..pipeline import steps
from . import tools


@dataclass
class Turn:
    text: str = ""                                   # assistant prose to show the user
    tool_calls: list[tuple[str, str, dict]] = field(default_factory=list)  # (id, name, input)
    raw_assistant: list = field(default_factory=list)  # assistant content blocks (for tool loop)


class ClaudeClient:
    def __init__(self, settings):
        self.settings = settings
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())

    async def turn(self, system: str, history: list[dict], version: str) -> Turn:
        """history: Anthropic-format messages. Returns assistant text + any tool calls."""
        last_exc: Exception | None = None
        for _ in range(self.settings.claude_max_retries + 1):
            try:
                resp = await asyncio.wait_for(
                    self._client.messages.create(
                        model=self.settings.launch11_model,
                        max_tokens=2000,
                        system=system,
                        tools=tools.tool_defs(version),
                        messages=history,
                    ),
                    timeout=self.settings.claude_timeout_s,
                )
                out = Turn(raw_assistant=resp.content)
                for block in resp.content:
                    if block.type == "text":
                        out.text += block.text
                    elif block.type == "tool_use":
                        out.tool_calls.append((block.id, block.name, dict(block.input)))
                return out
            except Exception as e:  # timeout / transient API error -> retry then give up
                last_exc = e
        raise last_exc  # surfaced to handler, reported to user without crashing the bot


def trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Sliding window (council P3): keep only the last N messages to bound context/cost."""
    return messages[-max_messages:] if len(messages) > max_messages else messages
