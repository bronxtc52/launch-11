# План — launch-11 бот, Фаза 3 (Telegram Stars)

**ТЗ:** `phase-3-billing.md` · **Класс:** L, **high-risk (деньги)** · **Код:** Sonnet

## Инварианты (нерушимые — деньги)

1. **Идемпотентность начисления** — `payments.charge_id` PRIMARY KEY; начисление кредита
   только если строка платежа реально вставлена (`INSERT … ON CONFLICT DO NOTHING`, проверка
   затронутых строк). Дубль webhook → 0 дополнительных кредитов.
2. **Атомарность списания** — `try_consume_entitlement` в ОДНОЙ транзакции: `INSERT billing …
   ON CONFLICT DO NOTHING` (гарантирует строку) → `SELECT … FOR UPDATE` → решение → мутация.
   Два конкурентных вызова для свежего юзера → ровно одно списание (row-lock сериализует).
3. **Гейт ДО действия** — право проверяется и слот списывается ДО `orch.start` и ДО любого
   вызова Claude. Нет права → счёт, без сессии и без Claude.
4. **Источник истины — сервер/БД**, не UI. Никаких «проверок в клиенте».

## Модель данных (миграция 003_billing.sql)

```sql
CREATE TABLE billing (
    tg_user_id   BIGINT PRIMARY KEY,
    free_used    INT NOT NULL DEFAULT 0,
    paid_credits INT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE payments (
    charge_id  TEXT PRIMARY KEY,           -- telegram_payment_charge_id — дедуп
    tg_user_id BIGINT NOT NULL,
    stars      INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_user ON payments (tg_user_id);
```

## Изменения по файлам

| Файл | Что |
|---|---|
| `db/migrations/003_billing.sql` | таблицы billing/payments |
| `db/repo.py` | + протокол `try_consume_entitlement`, `grant_paid_credit`, `get_billing` |
| `db/memory_repo.py` | реализация (asyncio.Lock эмулирует FOR UPDATE + ON CONFLICT дедуп) |
| `db/pg_repo.py` | реализация: списание в транзакции с `FOR UPDATE`; начисление `ON CONFLICT DO NOTHING` + проверка вставки |
| `billing/service.py` (нов.) | `BillingService`: `can_start/consume`, `on_successful_payment`, построение invoice-параметров (currency XTR, provider_token "", price из config) |
| `config.py` | + `free_runs`, `stars_price`, `stars_label`, `beta_allowlist` (опц.) |
| `app/turn.py` | `handle_incoming`: заменить access-gate на биллинг-гейт — при `session is None` вызвать `consume`; нет права → `on_needs_payment` (счёт), Claude НЕ звать |
| `tg/bot.py` | on_pick_version через тот же гейт; хендлеры `pre_checkout_query`→ok, `successful_payment`→grant+уведомление; `sendInvoice` при отказе; убрать старый allowlist-гейт (оставить опц. beta) |
| `tg/access.py` | `is_allowed` остаётся как опц. beta kill-switch (не основной гейт) |

## Задачи (TDD)

| # | Задача | Крит. | Зависит |
|---|---|---|---|
| T-301 | миграция 003 + репо-методы (InMemory/Pg) `try_consume_entitlement`/`grant_paid_credit`/`get_billing` + hermetic-тесты | 1,2,3,4 | — |
| T-302 | `BillingService` (consume, on_payment, invoice-params) + тесты | 3,4,8 | T-301 |
| T-303 | биллинг-гейт в `app/turn.py` (гейт ДО Claude, deny→счёт) + тест на мок-Claude «0 вызовов» | 5 | T-302 |
| T-304 | Telegram-хендлеры `pre_checkout_query`/`successful_payment` + `sendInvoice` (bot.py); логика вынесена в сервис для тестируемости | 6,7,8 | T-302 |
| T-305 | PG integration: гонка `try_consume` (одно списание) + персистентность billing/payments | 9,10 | T-301 |

**Порядок:** T-301 → T-302 → (T-303 ∥ T-304) → T-305.

## Тест-стратегия

- Hermetic (InMemoryRepo, тот же транзакционный контракт) — крит. 1-8. `BillingService` и гейт
  тестируются с мок-репо/мок-Claude; «гейт ДО Claude» = мок Claude получает 0 вызовов при отказе.
- Integration (живой PG) — крит. 9 (гонка `asyncio.gather` × N, итог `free_used=1`) и 10.
- Живая оплата Stars — ручная приёмка (нельзя без реального Telegram-платежа).

## Правки по совету моделей (v2, вердикт request_changes → приняты)

Совет (balanced 5 ролей; cheap-прогон деградировал — deepseek пустой/таймаут) дал 7 находок,
$0.645. Приняты — все про деньги:

- **[HIGH] Атомарное списание+создание сессии** (correctness-1 + security-2 + architect-2 +
  мой risk-note про гонку кликов). Вместо раздельных `try_consume_entitlement` + `orch.start`
  — ОДНА транзакция `start_session_with_entitlement(tg_user_id, slug, version, free_runs)`:
  lock/upsert billing → если активная сессия ЕСТЬ, вернуть её **без списания** → иначе проверить
  право (free_used++/paid_credits--) → создать сессию. Возврат: `(session | NEEDS_PAYMENT)`.
  Списание привязано к СОЗДАНИЮ сессии → идемпотентно к дублю update/двойному клику (single-active
  index + «списываем только если создали»), и нет TOCTOU (нет отдельного check-API — architect-2).
  Снимает и «компенсацию при падении старта»: списание и создание в одной транзакции.
- **[HIGH] Валидация платежа перед начислением** (security-1). В `sendInvoice` кладём
  `invoice_payload` (напр. `run:{user_id}`). В `successful_payment` начисляем ТОЛЬКО если
  `currency == "XTR"` И `total_amount == STARS_PRICE` И `invoice_payload` наш — иначе не начислять
  (лог + Sentry). `pre_checkout_query` — тоже проверить currency/amount перед `ok=True`.
- **[MEDIUM] Продуктовое решение** (product_risk-1): у существующих Phase-1/2 юзеров нет
  billing-строки → `free_used=0` → каждый получит 1 бесплатный прогон. Осознанно: бот НЕ в
  проде, платящих нет — **фреш-старт без бэкфилла**. Зафиксировано.
- **[MEDIUM] Fail-closed на раскатке** (product_risk-2): `BETA_ALLOWLIST` проверяется ДО
  биллинга; на раскатке — заполнить на время смоука, очистить после (шаг деплоя, не Фазы 3).

### Изменения критериев (в ТЗ добавлены 11-12, крит. 9 переформулирован)

- Крит. 9 (было «гонка списания») → «два конкурентных старта (текст ИЛИ клик) для свежего
  пользователя → ОДНА сессия и ОДНО списание (не два)».
- Крит. 11: `successful_payment` с `currency≠XTR` ИЛИ `total_amount≠STARS_PRICE` → кредит НЕ
  начисляется.
- Крит. 12: `invoice_payload` привязан к пользователю и проверяется при начислении.

### Дельта задач

- **T-301/302** → репо-метод `start_session_with_entitlement` (атомарно), `get_billing`
  остаётся read-only для отображения; `try_consume_entitlement` больше не публичный гейт.
- **T-304** → валидация currency/amount/payload в `pre_checkout` и `successful_payment`;
  `invoice_payload` в `sendInvoice`.

**Провенанс:** balanced-пресет (gpt-5.5 + deepseek; sonnet-5/gemini через OpenRouter пустые);
второй cheap-прогон DEGRADED (deepseek пустой content/таймаут) — disagreement-сигнал недоступен,
компенсирую внимательным Opus-судейством по money-инвариантам. Судья — оркестратор (Opus).

## Риски / грабли (из KB и Telegram API)

- **`pre_checkout_query` таймаут 10 с** — отвечать сразу `ok=True` (без тяжёлой работы в хендлере).
- **provider_token для XTR — пустая строка**; `currency="XTR"`; сумма в `LabeledPrice.amount`
  для Stars = число звёзд (не копейки).
- **Начисление только в `successful_payment`**, не в `pre_checkout` (там ещё не оплачено).
- **Гонка свежего billing-row:** без `INSERT … ON CONFLICT DO NOTHING` перед `FOR UPDATE`
  два конкурентных консьюма могут оба не найти строку и вставить/списать дважды — поэтому
  upsert строки billing первым шагом, затем lock.
- **beta-allowlist** (если задан) проверяется ДО биллинга — чтобы на раскатке случайный юзер
  не тратил Claude; по умолчанию пусто = не ограничивает.
