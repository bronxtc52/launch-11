# Bridge: Seysembay Pipeline ↔ GitHub Spec Kit

## Когда использовать гибридный подход

Метод Сейсембая силён в **зоне смысла** (шаги 1-7). GitHub Spec Kit силён в **зоне Bridge и Implementation** (структурированная спецификация + автогенерация задач + CLI-инструменты).

Объединение даёт лучшее из обоих:
- Глубокая проработка смысла от Сейсембая
- Инструментальная дисциплина от Spec Kit

## Когда стоит подключать Spec Kit

- Серьёзный продукт, который пойдёт в продакшен надолго
- Команда из 2+ человек (а не сам пользователь + Claude Code)
- Нужна формальная трассируемость спек → код
- Используется один из 30+ агентов, которые Spec Kit поддерживает (Claude Code, Copilot, Amazon Q и др.)

## Когда НЕ стоит

- Лендинг, прототип, MVP на выходные
- Один разработчик + Claude Code, без команды
- Идея ещё не проверена, можем поменяться 5 раз

## Структура гибрида

```
<product-slug>/                    # Рабочая папка Сейсембая (история)
├── 01-northern-star.md
├── 02-vision-story.md
├── ...
├── 07-story-sync-check.md
└── (шаги 8-10 не делаем здесь)

<product-slug>-repo/                # Репозиторий с Spec Kit
├── .specify/                       # Spec Kit metadata
├── constitution.md                 # Spec Kit "конституция" проекта
├── specs/
│   └── 001-<feature>/
│       ├── spec.md                 # Specify фаза
│       ├── plan.md                 # Plan фаза
│       └── tasks.md                # Tasks фаза
├── docs/
│   ├── vision.md                   # Vision Contract из Сейсембая
│   └── faq.md
├── adr/                            # ADR (общие для обоих методов)
└── CLAUDE.md
```

## Workflow гибрида

### Этап A: Шаги 1-7 Сейсембая (зона смысла)

Делается **как обычно** в рабочей папке. На выходе:
- `06-vision-contract-final.md`
- `06-faq.md`
- `07-story-sync-check.md` (Sync OK)
- `adr/` с продуктовыми ADR

### Этап B: Подключение Spec Kit

1. Создай новую папку для репозитория: `<product-slug>-repo/`
2. Инициализируй Spec Kit:

```bash
cd <product-slug>-repo
pip install specify-cli   # или npm, зависит от версии
specify init
```

3. Сгенерируется `.specify/` и стартовая структура.

### Этап C: Constitution.md

Это **главный файл Spec Kit** — "конституция проекта", immutable принципы. По сути, это то же, что финальный Vision Contract + продуктовые ADR, но в формате Spec Kit.

Структура `constitution.md`:

```markdown
# Constitution: <название продукта>

## Philosophy
<2-3 предложения из Vision Story>

## Non-negotiables
(Главные принципы, на которые соглашаются все участники)

- Принцип 1: ...
- Принцип 2: ...

## What we explicitly DO NOT do
(Блок D из Vision Contract)

- Не делаем X (см. ADR-002)
- Не делаем Y (см. ADR-005)

## Quality bar
- Все API должны иметь OpenAPI спеку
- Все БД-изменения — через миграции
- Минимум 70% coverage в core-логике
- ...

## Tech principles
- ...
```

### Этап D: Specify фаза (вместо шага 8)

Spec Kit команда:
```bash
specify
```

Это интерактивно создаст `specs/001-<feature>/spec.md`.

Из материалов Сейсембая берём:
- `06-vision-contract-final.md` → блоки A-C идут в spec.md
- Блок D (ограничения) → в constitution.md

### Этап E: Plan фаза (вместо шага 8 архитектуры)

```bash
plan
```

Создаст `specs/001-<feature>/plan.md`. Сюда идут:
- Архитектурные решения (то, что мы делали бы в `08-architecture.md`)
- Стек
- Структура БД

Технические ADR создаём параллельно в `adr/`.

### Этап F: Tasks фаза (вместо шага 10)

```bash
tasks
```

Spec Kit автоматически разобьёт plan.md на задачи в `specs/001-<feature>/tasks.md`.

Эти задачи будут структурированы стандартно для всех агентов — Claude Code, Copilot и др. их понимают одинаково.

### Этап G: Implement (шаг 11)

```bash
implement
```

Или вручную: `claude` (Claude Code прочитает constitution.md и текущий spec → tasks → начнёт работу).

## Что сохраняется от Сейсембая

Даже с Spec Kit, **уникальные ценности Сейсембая** сохраняются:

1. **Northern Star** — нет в Spec Kit. Кладём в `docs/north-star.md` и ссылаемся из constitution.md.
2. **Vision Story с метафорой** — нет в Spec Kit. В `docs/vision.md`.
3. **Story Sync Check** — нет в Spec Kit. Проводи руками раз в спринт, фиксируй в `docs/sync-checks/YYYY-MM-DD.md`.
4. **Продуктовые ADR** (целевая аудитория, отказы от фич) — нет в Spec Kit напрямую. Папка `adr/` подходит.

## Сравнительная таблица артефактов

| Сейсембай | GitHub Spec Kit | Что использовать в гибриде |
|-----------|-----------------|----------------------------|
| 01-northern-star.md | — | Сейсембай |
| 02-vision-story.md | — | Сейсембай |
| 03-vision-contract-draft.md | — | Сейсембай (история) |
| 04-research-brief.md | — | Сейсембай |
| 05-research-results.md | — | Сейсембай |
| 06-vision-contract-final.md | constitution.md (часть) + specs/*/spec.md (часть) | Гибрид |
| 06-faq.md | — | Сейсембай |
| 07-story-sync-check.md | — | Сейсембай (периодический) |
| 08-architecture.md | specs/*/plan.md | Spec Kit |
| 08-tech-spec.md | specs/*/plan.md (детально) | Spec Kit |
| 09-CLAUDE.md | constitution.md + ссылки | Гибрид |
| 10-BACKLOG.md | specs/*/tasks.md | Spec Kit |
| adr/ | (нет аналога) | Сейсембай (полностью) |

## Когда предлагать гибрид пользователю

В скилле, на **шаге 7 или начале шага 8**, можно спросить:

> Зона смысла закрыта. Теперь технические шаги — есть два варианта:
>
> 1. **Продолжаем чистый Сейсембай** — пишем architecture.md, tech-spec.md, BACKLOG.md руками. Хорошо для одиночных проектов и быстрых MVP.
>
> 2. **Подключаем GitHub Spec Kit** — он автоматизирует разбивку задач и даёт совместимость с другими AI-агентами. Хорошо для серьёзных продуктов и команд.
>
> Для этого продукта что выбираем?

Если пользователь выбрал гибрид — пройди этапы B-G выше.

## Источник

GitHub Spec Kit:
- Репозиторий: https://github.com/github/spec-kit
- В мае 2026: 93 000+ звёзд, v0.8.7, поддержка 30+ AI-агентов
- Документация: https://docs.specify.dev (если есть на момент использования)
