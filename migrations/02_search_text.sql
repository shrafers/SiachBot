-- Add column
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS search_text TEXT;

-- Trigger function: rebuilds search_text on insert/update
CREATE OR REPLACE FUNCTION update_recording_search_text()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_text := concat_ws(' ',
    NEW.title,
    (SELECT name FROM teachers WHERE id = NEW.teacher_id),
    (SELECT name FROM series   WHERE id = NEW.series_id),
    (SELECT string_agg(tag, ' ') FROM recording_tags WHERE recording_id = NEW.id)
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger
DROP TRIGGER IF EXISTS trg_recording_search_text ON recordings;
CREATE TRIGGER trg_recording_search_text
BEFORE INSERT OR UPDATE ON recordings
FOR EACH ROW EXECUTE FUNCTION update_recording_search_text();

-- Backfill existing rows
UPDATE recordings r
SET search_text = concat_ws(' ',
  r.title,
  (SELECT name FROM teachers WHERE id = r.teacher_id),
  (SELECT name FROM series   WHERE id = r.series_id),
  (SELECT string_agg(tag, ' ') FROM recording_tags WHERE recording_id = r.id)
);

-- GIN trigram index
CREATE INDEX IF NOT EXISTS idx_recordings_search_trgm
ON recordings USING GIN (search_text gin_trgm_ops);
