ALTER TABLE recordings ADD COLUMN IF NOT EXISTS hebrew_year TEXT;
CREATE INDEX IF NOT EXISTS recordings_hebrew_year_idx ON recordings(hebrew_year);
