"""Application-layer execution of LLM tool calls (council A3).

Validates arguments and routes to the orchestrator. Every failure mode is a
safe, non-advancing result — an unknown or malformed tool call must never crash
the bot (criterion 7).
"""
from __future__ import annotations

from dataclasses import dataclass

from .orchestrator import Orchestrator, StepError

ALLOWED_VERSIONS = {"lite", "full", "spec_only"}


@dataclass
class ToolResult:
    ok: bool
    message: str
    session: object            # the (possibly updated) Session
    spec: str | None = None    # set by a successful finish()


async def dispatch(orch: Orchestrator, session, tool_name: str, tool_input: dict) -> ToolResult:
    try:
        if tool_name == "save_artifact":
            step_id = tool_input.get("step_id")
            markdown = tool_input.get("markdown")
            if not isinstance(step_id, str) or not isinstance(markdown, str):
                return ToolResult(False, "save_artifact: нужны step_id и markdown", session)
            session = await orch.save_artifact(session, step_id, markdown)
            return ToolResult(True, f"✅ Шаг {step_id} зафиксирован", session)

        if tool_name == "set_version":
            version = tool_input.get("version")
            if version not in ALLOWED_VERSIONS:
                return ToolResult(False, f"неизвестная версия: {version}", session)
            session = await orch.set_version(session, version)
            return ToolResult(True, f"версия: {version}", session)

        if tool_name == "create_adr":
            title = tool_input.get("title")
            markdown = tool_input.get("markdown")
            if not isinstance(title, str) or not isinstance(markdown, str):
                return ToolResult(False, "create_adr: нужны title и markdown", session)
            n = await orch.create_adr(session, title, markdown)
            return ToolResult(True, f"✅ ADR-{n} зафиксирован: {title}", session)

        if tool_name == "finish":
            spec = await orch.finish(session)
            return ToolResult(True, "готово", session, spec=spec)

        # criterion 7 — unknown tool is handled, not crashed
        return ToolResult(False, f"неизвестный инструмент: {tool_name}", session)

    except StepError as e:
        return ToolResult(False, e.reason, session)
    except Exception as e:  # defensive: never let a tool call take down the loop
        return ToolResult(False, f"ошибка выполнения инструмента: {type(e).__name__}", session)
