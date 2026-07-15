CREATE TABLE IF NOT EXISTS sessions (
    id           BIGSERIAL PRIMARY KEY,
    tg_user_id   BIGINT      NOT NULL,
    slug         TEXT        NOT NULL,
    version      TEXT        NOT NULL,
    current_step TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Exactly one active session per user (council A1/C1: kills the double-/start race)
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session
    ON sessions (tg_user_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS artifacts (
    id         BIGSERIAL PRIMARY KEY,
    session_id BIGINT      NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    step_id    TEXT        NOT NULL,
    markdown   TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, step_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    session_id BIGINT      NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    role       TEXT        NOT NULL,
    text       TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id);
