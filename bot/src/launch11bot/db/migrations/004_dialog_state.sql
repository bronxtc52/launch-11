ALTER TABLE sessions ADD COLUMN IF NOT EXISTS current_question TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_verdict TEXT;

-- verdict is a closed enum; enforce it at the storage boundary too (council architect-4).
-- ADD CONSTRAINT has no IF NOT EXISTS in PG: guard it, or a re-applied migration (ledger
-- reset / manual edit) raises duplicate_object and the bot fails to start.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sessions_last_verdict_chk'
    ) THEN
        ALTER TABLE sessions ADD CONSTRAINT sessions_last_verdict_chk
            CHECK (last_verdict IS NULL OR last_verdict IN ('answer', 'partial', 'offtopic'));
    END IF;
END
$$;
