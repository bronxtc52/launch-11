CREATE TABLE IF NOT EXISTS billing (
    tg_user_id   BIGINT PRIMARY KEY,
    free_used    INT NOT NULL DEFAULT 0,
    paid_credits INT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Payment ledger. PK on the Telegram charge id = idempotent crediting (KB lesson).
CREATE TABLE IF NOT EXISTS payments (
    charge_id  TEXT PRIMARY KEY,
    tg_user_id BIGINT      NOT NULL,
    stars      INT         NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (tg_user_id);
