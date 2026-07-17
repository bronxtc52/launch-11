# launch-11

## Что это

Репо про **пайплайн запуска продуктов Маргулана Сейсембая** (11 шагов: Смысл → Bridge →
Реализация). Две вещи в одном месте:

- **методика** — `claude-code/seysembay-pipeline/` (скилл для Claude Code), `claude-ai/SKILL.md`
  (inline-версия), `guide.md`;
- **`bot/`** — Telegram-бот **@launch_11_bot**, который ведёт человека по этому пайплайну
  сократическим диалогом и отдаёт готовую `spec.md` документом.

Мозг бота — та же методика: `claude-ai/SKILL.md` → системный промпт + инструкции шагов.

## Stack (bot/)

Python 3.12 · aiogram 3 (long-polling) · Claude Sonnet 5 (tool-use) · Postgres 16 · Sentry.

```bash
cd bot
bash deploy/fetch-env.sh dev .env     # секреты из kv-bronxtc-dev (namespace launch11--dev--*)
docker compose up -d --build          # бот + postgres
python -m pytest -q --ignore=tests/test_persistence_pg.py          # hermetic
TEST_DATABASE_URL=postgresql://... python -m pytest -q             # + integration
```

## Архитектурный принцип (не нарушать)

**Свободный диалог модели, но детерминизм переходов — через код.** Модель разговаривает;
шаги двигает `pipeline/orchestrator.py`.

## Инварианты, купленные болью — ломать нельзя

Каждый закрыт регресс-тестом. Если тест мешает — это не повод его править: он там потому,
что баг уже случался у живых людей.

1. **Модель может задерживать прогресс, но не может его остановить.**
   `resolve_answer` — единственный владелец переходов. `clarify_count`/`clarify_budget`
   персистятся и **не сбрасываются** при переспросе. **Одна ветка** на все не-`answer`
   вердикты: не добавляй `if verdict == "..."` — это whack-a-mole, мы прошли его дважды.
   → `tests/test_progress_invariant.py`
2. **Вердикт модели ничего не решает** — он вход контроллера. `last_verdict` = наблюдаемость.
3. **Закрытый выбор судит КОД**, не LLM (`pipeline/choice.py`). Человек выбрал предложенный
   вариант — засчитано, даже если модель твердит `partial`.
4. **Один вопрос за сообщение.** Вопросы — только через `ask_question`; валидируется **весь
   текст**, который увидит человек (`validate_rendered`), потому что свалка уезжала в `preamble`.
5. **Ничего не терять.** Всё, что видел человек, обязано попасть в транскрипт (`send_question`):
   иначе в БД два `user` подряд → `normalize_history` их склеит → модель не увидит своих
   переспросов → вечная петля. Детектор дешёвый: `SELECT id, role FROM messages ORDER BY id`,
   ищи два `user` кряду.
6. **Никогда не бросать человека**: ход не может закончиться ни молча, ни «высказался, но
   ничего не спросил». Обрезанный по `max_tokens` ответ пользователю **не пересылается**.
7. **Служебные сообщения с ролью `user`** (tool_result, коррекции) обязаны помечать себя
   служебными и цитировать реальную реплику — иначе модель оценивает ИХ и выносит `offtopic`
   на валидный ответ. Урок: `knowledge-base/lessons/llm-history-must-match-reality.md`.
8. **Валидатор чинит, а не уничтожает.** Список **утверждений** — контент; запрещены вопросы
   и свалки требований (≥2 императива). Мы уже удалили формулировку, которую просили подтвердить.
9. **Первая реплика человека не называет продукт** — иначе получается `не-понял-spec.md`.
   Имя даёт модель через `set_product_name`.
10. **Один токен = один поллер.** Поднимешь прод — гаси локальный `docker compose down`,
    иначе два поллера дерутся за `getUpdates` (409) и бот отвечает через раз.

## Границы

- Прод-деплой — **только через CI** (`.github/workflows/deploy.yml`, OIDC). Руками с mh-central
  нельзя: у MSI нет write на RG, и это by design.
- Секреты — только Key Vault (`launch11--{production,dev}--*`), в репо плейсхолдеры.
  **Репо публичный** — реальные Telegram-id сюда не коммитить.
- Тексты для человека — по-русски; LLM-вывод в Telegram идёт через `tg/sanitize.py`
  (`md_to_telegram_html`, вендор из Avicenna).

## Отладка диалога

Начинай **с транскрипта, а не с кода** — рассинхрон видно глазами, без чтения кода:

```bash
# прод: логи решений модели и контроллера
az containerapp logs show -n ca-launch11-bot -g rg-launch11-prod --tail 60 \
  | grep -E "tool=|controller:|contract violation|truncated|stranded"

# транскрипт (PG прода; строка подключения — в KV launch11--production--DATABASE-URL)
# два `user` подряд = бот что-то сказал и НЕ сохранил → модель этого не видит → петля
SELECT id, role, left(text,80) FROM messages ORDER BY id;
```

За сессию 2026-07-16 корень **четыре раза подряд** оказывался в наших текстах/лимитах, а не
в модели: «задай 5-7 вопросов» → служебная роль `user` → «варианты с фокусами» → `max_tokens`.

## Статус

**ПРОД с 2026-07-17**, публичный. `ca-launch11-bot` в `rg-launch11-prod` (northeurope),
ревизия Healthy, 1/1 реплика. Локальный docker-compose **погашен** — иначе 409.

```bash
az containerapp revision list -n ca-launch11-bot -g rg-launch11-prod -o table   # живая ревизия
az containerapp logs show -n ca-launch11-bot -g rg-launch11-prod --tail 40      # логи прода
```

Деплой — **push в main** (CI сам: build → create-or-update → smoke до Healthy → rollback).
Руками `az containerapp update` не делать: это break-glass, и у MSI mh-central всё равно нет прав.

**Хвосты:** живой платёж звёздами не проверен ни разу; ночного дампа PG нет (PITR 7д по
умолчанию); Sentry smoke из прода не делали. Детали — строка `launch-11` в `~/projects/CLAUDE.md`.
