ALTER TABLE sessions ADD COLUMN IF NOT EXISTS current_question TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_verdict TEXT;

-- verdict is a closed enum; enforce it at the storage boundary too (council architect-4)
ALTER TABLE sessions ADD CONSTRAINT sessions_last_verdict_chk
    CHECK (last_verdict IS NULL OR last_verdict IN ('answer', 'partial', 'offtopic'));
