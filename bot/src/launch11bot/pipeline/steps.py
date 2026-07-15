"""Versioned pipeline registry.

Steps are DATA, not code (council A5): adding the Full 11-step pipeline in
Phase 2 means adding an entry to PIPELINES, not touching the orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    id: str
    zone: str          # Смысл | Bridge | Реализация
    title: str
    goal: str
    instruction: str   # the step-specific guidance handed to the LLM


LITE_STEPS: list[Step] = [
    Step(
        "L1", "Смысл", "Идея, Northern Star и метафора",
        "Превратить сырую идею в одну фразу про успех и метафору «это как X, но для Y».",
        "Выуди у пользователя идею сократическими вопросами (кто страдает, какой костыль "
        "сейчас, одна главная фича, как поймём что помогло). Предложи 3 варианта Northern "
        "Star (скорость / регулярность / результат) и метафору. Northern Star — поведенческая "
        "или продуктовая метрика, НЕ выручка. Зафиксируй артефакт: Northern Star, кто "
        "пользователь, какая боль, метафора одной фразой, лифт-питч 30 секунд.",
    ),
    Step(
        "L2", "Смысл", "Vision Contract",
        "Зафиксировать договорённости: проблема, аудитория, решение, границы, успех.",
        "Идите по блокам ПО ОДНОМУ: A) проблема (конкретная боль, 2-3 примера); "
        "B) аудитория (одна персона, не сегмент); C) решение (3-5 сценариев, что в v1, "
        "что отложено); D) ГРАНИЦЫ — минимум 5 пунктов «НЕ делаем» (самый важный блок для "
        "дисциплины); E) успех (Northern Star + 2-3 измеримые метрики). Не пиши блок без "
        "подтверждения пользователя.",
    ),
    Step(
        "L3", "Bridge", "Короткая архитектура",
        "Перевести Vision в технический скелет: стек и хостинг.",
        "Предложи 1-2 варианта стека (frontend/backend/БД/хостинг/авторизация) с плюсами и "
        "минусами, дай рекомендацию, получи выбор пользователя. Держись простейшего "
        "работающего подхода — микросервисы это для v3, не для v1. Зафиксируй выбранный стек "
        "и 1-2 ключевых технических решения с обоснованием.",
    ),
    Step(
        "L4", "Bridge", "Контекст и задачи",
        "Собрать краткий CLAUDE.md-контекст и список задач для разработки.",
        "Сведи всё в короткий рабочий контекст: Northern Star одной фразой, целевой "
        "пользователь, «НЕ делаем в v1» (3-5 пунктов), стек. Затем разбей v1 на 5-10 задач "
        "по 1-3 часа каждая, с кратким Definition of Done. Задача «реализовать модуль X» — "
        "это эпик, разбивай мельче.",
    ),
]

PIPELINES: dict[str, list[Step]] = {
    "lite": LITE_STEPS,
    # "full": FULL_STEPS,        # Phase 2
    # "spec_only": SPEC_STEPS,   # Phase 2
}


def step_ids(version: str) -> list[str]:
    return [s.id for s in PIPELINES.get(version, [])]


def get_step(version: str, step_id: str) -> Step | None:
    for s in PIPELINES.get(version, []):
        if s.id == step_id:
            return s
    return None


def first_step_id(version: str) -> str:
    return PIPELINES[version][0].id


def next_step_id(version: str, step_id: str) -> str | None:
    ids = step_ids(version)
    i = ids.index(step_id)
    return ids[i + 1] if i + 1 < len(ids) else None


def step_index(version: str, step_id: str) -> int:
    """Position of step_id in the pipeline, or -1 if unknown."""
    ids = step_ids(version)
    return ids.index(step_id) if step_id in ids else -1
