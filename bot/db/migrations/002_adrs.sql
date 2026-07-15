CREATE TABLE IF NOT EXISTS adrs (
    id         BIGSERIAL PRIMARY KEY,
    session_id BIGINT      NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    n          INT         NOT NULL,
    title      TEXT        NOT NULL,
    markdown   TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, n)
);

CREATE INDEX IF NOT EXISTS idx_adrs_session ON adrs (session_id);
