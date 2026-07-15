# План — launch-11 бот, Фаза 1 (петля)

**ТЗ:** `phase-1-loop.md` · **Класс:** L, не high-risk · **Модель кода:** Sonnet 5

## Ключевые архитектурные решения

1. **Оркестратор — над Repo-интерфейсом, не над БД напрямую.** Вся FSM-логика
   (переход шагов, гейт `save_artifact`, гейт `finish`) работает через `Repo`-протокол.
   Две реализации: `InMemoryRepo` (для быстрых hermetic-тестов) и `PgRepo` (asyncpg).
   → крит. 3-7 тестируются без Postgres; крит. 8 — отдельным integration-тестом на живой PG.
2. **Шаги — данные, не код.** `steps.py` держит список Lite-шагов; оркестратор
   generic. Фаза 2 (Full 11) = добавить строки, логику не трогаем.
3. **Детерминизм через tool-use.** Claude ведёт свободный диалог, но структурные
   переходы — только через инструменты. Диспетчер валидирует имя/аргументы,
   неизвестный инструмент → безопасная ошибка (не краш) — крит. 7.
4. **Санитайзер вендорим** из Avicenna (`md_to_telegram_html`), порядок regex строгий
   (`html.escape` первым). Чанковка `chunk_html` по границам строк — крит. 1, 2.
5. **Long-polling без ingress, single-replica** (грабля крэш-лупа) — фиксируется в
   Dockerfile/compose и будущем ACA-манифесте (ACA — не эта фаза).

## Структура

```
bot/
├── pyproject.toml                # aiogram3, anthropic, asyncpg, sentry-sdk, pydantic-settings, pytest, pytest-asyncio
├── docker-compose.yml            # bot + postgres:16
├── Dockerfile                    # python:3.12-slim, без ingress
├── .env.example                  # LAUNCH11_BOT_TOKEN, ANTHROPIC_API_KEY, DATABASE_URL, SENTRY_DSN
├── deploy/fetch-env.sh           # KV → .env (namespace launch11--production--*); заглушка-конвенция
├── src/launch11bot/
│   ├── config.py                 # pydantic-settings, SecretStr
│   ├── main.py                   # entrypoint: Sentry init → проверка токена (fatal) → start_polling
│   ├── db/
│   │   ├── schema.sql            # sessions / artifacts / messages (UNIQUE(session_id, step_id))
│   │   ├── repo.py               # Repo Protocol + PgRepo (asyncpg)
│   │   └── memory_repo.py        # InMemoryRepo (тот же Protocol)
│   ├── pipeline/
│   │   ├── steps.py              # LITE_STEPS: [{id, zone, title, goal, instruction}]
│   │   ├── orchestrator.py       # start_session / handle_save_artifact(guard) / can_finish / advance
│   │   └── assemble.py           # artifacts → <slug>-spec.md (порядок L1→L4 + заголовок)
│   ├── llm/
│   │   ├── tools.py              # JSON-схемы save_artifact/set_version/finish + dispatch()
│   │   ├── system_prompt.py      # system = адаптация claude-ai/SKILL.md + инструкция шага
│   │   └── client.py             # Anthropic wrapper (в тестах мок)
│   └── tg/
│       ├── sanitize.py           # md_to_telegram_html (вендор) + chunk_html
│       ├── keyboards.py          # inline: Дальше / Переформулировать / Прогресс; А/Б/В
│       └── bot.py                # /start, message, callbacks; sendDocument на finish
└── tests/
    ├── test_sanitize.py          # крит. 1, 2
    ├── test_orchestrator.py      # крит. 3, 4, 5, 6 (InMemoryRepo)
    ├── test_tools.py             # крит. 7
    ├── test_assemble.py          # крит. 6 (сборка)
    └── test_persistence_pg.py    # крит. 8 (живой PG, skip если нет DATABASE_URL)
```

## Задачи (TDD — тесты отдельным коммитом до реализации)

| # | Задача | Размер | Крит. | Зависит |
|---|---|---|---|---|
| T-001 | Скелет: pyproject, config, docker-compose, Dockerfile, .env.example, dirs | S | — | — |
| T-002 | Санитайзер: вендор `md_to_telegram_html` + `chunk_html` + тесты | M | 1,2 | T-001 |
| T-003 | БД: `schema.sql`, `Repo` Protocol, `InMemoryRepo`, `PgRepo` | M | (8) | T-001 |
| T-004 | `steps.py` (Lite) + `orchestrator` (guard перехода, finish-гейт, идемпотентность) + тесты | M | 3,4,5,6 | T-003 |
| T-005 | `assemble.py` сборка `spec.md` + тест | S | 6 | T-004 |
| T-006 | `tools.py`: схемы инструментов + `dispatch()` + тест (неизвестный тул → ошибка) | M | 7 | T-004 |
| T-007 | `system_prompt.py` (из SKILL.md + шаг) + `client.py` (Anthropic, мок в тестах) | M | — | T-006 |
| T-008 | `tg/bot.py`: /start, message-loop, callbacks, sendDocument; keyboards; wiring | M | — | T-002,05,07 |
| T-009 | Integration-тест персистентности на живом PG (skip без DATABASE_URL) | S | 8 | T-003,08 |
| T-010 | `main.py` entrypoint (Sentry→токен→polling) + локальный smoke `docker-compose up` | S | — | все |

**План запуска:** T-001 → (T-002 ∥ T-003) → T-004 → (T-005 ∥ T-006) → T-007 → T-008 → T-009 → T-010.

## Тест-стратегия

- **Hermetic (без внешних сервисов):** санитайзер, оркестратор (InMemoryRepo), tools, assemble.
  Зелёные без docker/сети/ключей. Покрывают крит. 1-7.
- **Integration:** `test_persistence_pg.py` — на живом PG (из compose или `DATABASE_URL`),
  крит. 8; `pytest.mark.skipif` без URL, чтобы не блокировать hermetic-прогон.
- **Claude/Telegram — мокаются** в unit; живой прогон с реальным ботом+ключом = ручная
  приёмка после зелёных юнитов (evidence в отчёте).

## Границы плана (подтверждение из ТЗ)

Не входит: биллинг/Stars, Full 11 шагов, ADR/BACKLOG/zip, web-research, **прод-деплой ACA
и любое создание Azure-ресурсов** (красная зона — отдельным шагом с явным «ок»).

## Правки по ревью совета моделей (v2, вердикт request_changes → приняты)

Совет (architect/security/correctness/performance/product_risk, balanced) дал 18 находок.
Приняты все — дёшевы и большинство **страхует от переписывания в Фазах 2-3**:

**Безопасность / стоимость (Фаза 1 — публичный бот без биллинга):**
- **S1. Никаких prod-секретов в локальный `.env`.** `fetch-env.sh` в Фазе 1 тянет только
  из `launch11--dev--*` (или ручной тест-бот). Отдельный **тестовый** bot-token, не боевой.
- **S2/PR1. Access-gate до вызова Claude.** `ALLOWED_TG_USER_IDS` в config; хендлеры отклоняют
  чужих ДО обращения к Claude → кран не публичный, пока нет биллинга (Фаза 3). Крит. приёмки.
- **S3. Границы аргументов инструментов.** `step_id` — enum; `markdown` — лимит байт/шаг;
  общий лимит на сессию; невалидное — безопасный отказ без продвижения шага. Крит. приёмки.
- **S4. Sentry `before_send`-скраббер** + PII off: вырезать тела Telegram-update, тексты,
  аргументы инструментов, токены. Юнит-тест редакции.

**Архитектура (страховка от Фаз 2-3):**
- **A5. Версионируемый реестр пайплайнов** `PIPELINES = {version: StepSequence}` вместо голого
  `LITE_STEPS`. Оркестратор берёт последовательность из `session.version`; `assemble`/`finish`
  идут по ней, не по хардкоду L1→L4. **Прямо снимает риск переписывания под Full 11.**
- **A6. Граница миграций.** `db/migrations/001_init.sql` + простой упорядоченный применятель
  (не единственный `schema.sql`) — чтобы Фаза 3 (`payments`) легла миграцией, а не ALTER-ом руками.
- **A1/C1. Атомарный переход шага + одна активная сессия.** guard+upsert+advance — в ОДНОЙ
  транзакции `PgRepo` (conditional update/row-lock); `InMemoryRepo` эмулирует тот же контракт.
  Partial unique index `WHERE status='active'` на `sessions(tg_user_id)`. Крит. приёмки (гонка).
- **A3/A4. Схемы инструментов ≠ диспетчер.** `llm/tools.py` — чистые Anthropic-схемы+парсер;
  исполнение — `pipeline/tool_dispatcher.py` (зависит от orchestrator+Repo). Методы транскрипта
  — явно в Repo-протоколе.
- **A2/PR2. `set_version` — enum `["lite"]`** в Фазе 1 (не рекламируем full/spec_only Claude'у);
  диспетчер безопасно отклоняет `full`/`spec_only`. Крит. приёмки.

**Производительность / корректность:**
- **P1.** индекс `CREATE INDEX idx_messages_session ON messages(session_id)`.
- **P2.** таймаут на вызов Claude (`asyncio.wait_for`/SDK-timeout) + кап ретраев.
- **P3.** скользящее окно контекста `MAX_CONTEXT_MESSAGES` (не слать всю историю → контекст/деньги).
- **C2.** чанковка: строковая (как Avicenna) **+ безопасный char-level split для строк >4096**
  (вне тегов) — усиление крит. 2.
- **PR3.** минимальная политика хранения: команда `/reset` (удаление сессии) + заметка о retention.

### Новые/изменённые критерии приёмки (добавка к ТЗ §Критерии)

9. **Access-gate:** апдейт от `tg_user_id` вне `ALLOWED_TG_USER_IDS` → бот отвечает отказом и
   **Claude не вызывается** (мок Claude не получает вызовов).
10. **set_version:** `dispatch(set_version, "lite")` — ок; `"full"`/`"spec_only"` → безопасный
    отказ без смены состояния.
11. **Границы аргументов:** `save_artifact` с `markdown` больше лимита или неизвестным `step_id`
    → отказ, `current_step` не двигается, артефакт не пишется.
12. **Атомарность/гонка (integration, PG):** два конкурентных `start_session` для одного
    `tg_user_id` → ровно одна строка `status=active` (partial unique index держит).
13. **Sentry-скраббер:** `before_send` на событии с текстом сообщения/токеном → в исходящем
    payload их нет (юнит).

### Дельта задач

- **T-003** дополняется: `db/migrations/001_init.sql` + применятель; partial unique index;
  атомарные методы перехода в `Repo` (транзакция в `PgRepo`).
- **T-004** использует `PIPELINES[version]`, а не `LITE_STEPS`; переход — атомарный метод Repo.
- **T-006** переименовать логику исполнения в `pipeline/tool_dispatcher.py`; `set_version` enum
  `["lite"]`; границы аргументов (крит. 10, 11).
- **Новая T-004a** (config+хендлер): access-gate `ALLOWED_TG_USER_IDS` (крит. 9).
- **T-007** дополняется таймаутом+ретрай-капом Claude (P2) и скользящим окном контекста (P3).
- **T-010** дополняется Sentry `before_send`-скраббером (крит. 13) и командой `/reset` (PR3).
- **T-002** усиливается char-level split для строк >4096 (C2).

**Провенанс ревью:** balanced-пресет; роли отвечали gpt-5.5 / deepseek-v4-pro (sonnet-5 и
gemini через OpenRouter вернули пустой content — выпали); судья — оркестратор (Opus, иной вендор,
чем ревьюеры). Стоимость $1.37. Отчёт — `.review/report.md`, консенсус — `.review/consensus.json`.

## Открытые риски

- **Стоимость Claude на публике** — снимается только в Фазе 3 (лимиты/биллинг). В Фазе 1
  бот запускается лишь для теста (свой tg-user), кран не публичный.
- **Схема БД** заложена под Фазу 3 частично (нет `payments` — добавим миграцией тогда;
  `sessions` уже с `version` и `status`, расширяемо).
