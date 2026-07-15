"""Pure Anthropic tool schemas (council A3: no execution here).

Execution lives in pipeline/tool_dispatcher.py.
"""
from __future__ import annotations

from ..pipeline import steps


def tool_defs(version: str) -> list[dict]:
    ids = steps.step_ids(version)
    return [
        {
            "name": "save_artifact",
            "description": (
                "Зафиксировать готовый markdown-артефакт текущего шага пайплайна. "
                "Вызывай ТОЛЬКО после того, как пользователь подтвердил формулировку. "
                "step_id должен быть текущим шагом."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string", "enum": ids},
                    "markdown": {"type": "string", "description": "Содержимое артефакта в markdown."},
                },
                "required": ["step_id", "markdown"],
            },
        },
        {
            "name": "set_version",
            "description": (
                "Выбрать версию пайплайна: 'full' (11 шагов), 'lite' (сжато), "
                "'spec_only' (только техчасть 8-11). Сменить можно только пока не сохранён "
                "ни один артефакт."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "version": {"type": "string", "enum": ["lite", "full", "spec_only"]},
                },
                "required": ["version"],
            },
        },
        {
            "name": "create_adr",
            "description": (
                "Зафиксировать архитектурное решение (ADR) со сквозной нумерацией. "
                "Вызывай на шагах фиксации продуктовых (F6) и технических (F8) решений."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Краткое название решения."},
                    "markdown": {"type": "string", "description": "Тело ADR в markdown."},
                },
                "required": ["title", "markdown"],
            },
        },
        {
            "name": "finish",
            "description": "Собрать финальную spec.md. Доступно только когда все шаги заполнены.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]
