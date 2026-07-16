-- The progress invariant, persisted: the model may delay, never stop.
-- clarify_count is bound by clarify_budget and is NOT reset by a re-ask — that reset is
-- precisely what made the loop invisible (ask_question used to wipe last_verdict).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clarify_count INT NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clarify_budget INT NOT NULL DEFAULT 2;
-- options offered with the open question: a closed choice is resolved by CODE, not by the LLM
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS current_options TEXT;  -- JSON array or NULL

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sessions_clarify_budget_chk') THEN
        -- the invariant is checkable in SQL: no open run may exceed its budget
        ALTER TABLE sessions ADD CONSTRAINT sessions_clarify_budget_chk
            CHECK (clarify_count <= clarify_budget);
    END IF;
END
$$;
