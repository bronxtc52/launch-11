-- Строка сессии становится РЕЕСТРОМ списания.
--
-- Инцидент 2026-07-17: право списывалось при /start, а «начать заново» удаляло сессию без
-- возврата → человек оплатил наш сбой (Anthropic 529 семь минут). Возврат нельзя сделать
-- идемпотентным, если строку, которая помнит списание, удаляют: DELETE уносит вместе с ней
-- защиту от повторного возврата. Отсюда: сессию НЕ удаляем, помечаем 'abandoned'.
--
-- Словарь статусов: active | finished | abandoned.

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS consumed TEXT    NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS refunded BOOLEAN NOT NULL DEFAULT false;

-- PG не умеет ADD CONSTRAINT IF NOT EXISTS; ledger schema_migrations защищает от повтора,
-- но ручной прогон миграции не должен падать.
DO $$
BEGIN
    ALTER TABLE sessions
        ADD CONSTRAINT sessions_consumed_chk CHECK (consumed IN ('free', 'paid', 'none'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Бэкфилл не нужен: 'none' = «списания не помним, возвращать нечего» — честный дефолт для
-- старых строк. Гадать корзину опаснее: ошибка в пользу free напечатала бы бесплатный прогон.
