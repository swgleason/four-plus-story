-- Add narrator gender classification to stories.

DO $$ BEGIN
    CREATE TYPE narrator_gender AS ENUM ('male', 'female', 'unknown');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE stories
    ADD COLUMN IF NOT EXISTS narrator_gender narrator_gender NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_stories_narrator_gender
    ON stories(narrator_gender);
