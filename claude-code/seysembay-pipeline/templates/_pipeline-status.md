# Pipeline Status: <product-name>

**Версия пайплайна:** Full | Lite | Spec-only
**Начат:** YYYY-MM-DD
**Текущий шаг:** N/11
**Связан с проектом:** <Marine Health / MePost / Standalone / ...>

## Прогресс по шагам

### Зона Смысла

- [ ] Шаг 1: Brainstorming + Northern Star → `01-northern-star.md`
- [ ] Шаг 2: Vision Story с метафорой → `02-vision-story.md`
- [ ] Шаг 3: Vision Contract Draft (A-E) → `03-vision-contract-draft.md`
- [ ] Шаг 4: Research Brief → `04-research-brief.md`
- [ ] Шаг 5: Research → `05-research-results.md`
- [ ] Шаг 6: Final Contract + ADR + FAQ → `06-vision-contract-final.md`, `06-faq.md`, `adr/`
- [ ] Шаг 7: Story Sync Check → `07-story-sync-check.md`

### Зона Bridge

- [ ] Шаг 8: Architecture + Tech-spec + ADR → `08-architecture.md`, `08-tech-spec.md`
- [ ] Шаг 9: CLAUDE.md + документация → `09-CLAUDE.md`, `09-README-for-repo.md`
- [ ] Шаг 10: BACKLOG → `10-BACKLOG.md`

### Зона Реализации

- [ ] Шаг 11: Handoff в Claude Code → создан `<product-slug>-repo/`, передан BACKLOG

## Принятые ADR

(Заполняется по ходу шагов 6, 8)

### Продуктовые
- _Пока пусто. Появятся на шаге 6._

### Технические
- _Пока пусто. Появятся на шаге 8._

## Контекст

**Идея в одной фразе:** <будет заполнено после шага 1>
**Целевая аудитория:** <будет заполнено после шага 3>
**Стек (если уже понятен):** <будет заполнено после шага 8>

## Карта переименования файлов при переезде в репозиторий

(Заполняется на шаге 9)

| Рабочая папка | → | Репозиторий |
|---------------|---|-------------|
| `01-northern-star.md` | → | (не переезжает, остаётся как история) |
| `02-vision-story.md` | → | `docs/vision/story.md` (опционально) |
| `03-vision-contract-draft.md` | → | (не переезжает) |
| `04-research-brief.md` | → | (не переезжает) |
| `05-research-results.md` | → | (не переезжает) |
| `06-vision-contract-final.md` | → | `docs/vision.md` |
| `06-faq.md` | → | `docs/faq.md` |
| `07-story-sync-check.md` | → | (не переезжает) |
| `08-architecture.md` | → | `docs/architecture.md` |
| `08-tech-spec.md` | → | `docs/tech-spec.md` |
| `09-CLAUDE.md` | → | `CLAUDE.md` (корень) |
| `09-README-for-repo.md` | → | `README.md` (корень) |
| `10-BACKLOG.md` | → | `BACKLOG.md` (корень) |
| `adr/` | → | `adr/` |

## Заметки и отклонения от пайплайна

(Сюда записывай важные моменты по ходу процесса. Например: "На шаге 5 решили пропустить интервью с пользователями из-за времени, перепроверим через 2 месяца после запуска")

## Что дальше

(Обновляется автоматически скиллом)

**Текущая задача:** Шаг N, описание

**Следующие шаги:** N+1, N+2
