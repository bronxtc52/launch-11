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
            "description": "Выбрать версию пайплайна. В текущей фазе доступна только 'lite'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "version": {"type": "string", "enum": ["lite"]},
                },
                "required": ["version"],
            },
        },
        {
            "name": "finish",
            "description": "Собрать финальную spec.md. Доступно только когда все шаги заполнены.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]
