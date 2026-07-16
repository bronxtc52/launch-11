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
            "name": "ask_question",
            "description": (
                "ЕДИНСТВЕННЫЙ способ задать вопрос пользователю. Ровно ОДИН короткий вопрос "
                "за раз — не список, не нумерация, не несколько вопросов в одном тексте. "
                "После вызова ход заканчивается: ждём ответ человека. Вопросы в свободном "
                "тексте запрещены — только через этот инструмент."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string",
                                 "description": "Ровно один вопрос, коротко, без списков."},
                    "preamble": {"type": "string",
                                 "description": "Опционально: 1-2 фразы контекста перед вопросом."},
                    "options": {"type": "array", "items": {"type": "string"},
                                "description": "ОБЯЗАТЕЛЬНО, если предлагаешь выбор из вариантов: "
                                               "перечисли их точными короткими словами (например "
                                               "['скорость','регулярность','результат']). Код сам "
                                               "засчитает выбор человека — не оценивай его сам."},
                },
                "required": ["question"],
            },
        },
        {
            "name": "assess_answer",
            "description": (
                "Оцени последнюю реплику человека относительно заданного вопроса. Вызывай "
                "ПЕРВЫМ, пока есть открытый вопрос. Это ТВОЁ МНЕНИЕ, а не решение: двигать "
                "ли шаг, решает код — он же скажет тебе, что делать дальше. "
                "'answer' — ответил по существу (выбор одного из предложенных вариантов = "
                "полноценный ответ!); 'partial' — ответил частично (укажи missing); "
                "'offtopic' — это не ответ на вопрос. Число уточнений ограничено: "
                "исчерпав его, код закроет вопрос сам."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["answer", "partial", "offtopic"]},
                    "missing": {"type": "string", "description": "Чего не хватает при 'partial'."},
                },
                "required": ["verdict"],
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
