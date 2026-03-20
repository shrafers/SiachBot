-- Add "חבורות - זוהר מאור" as a new subject area,
-- with each chavura as a sub-discipline under it.
-- Run in Supabase SQL editor.

INSERT INTO subject_areas (name)
VALUES ('חבורות - זוהר מאור')
ON CONFLICT (name) DO NOTHING;

DO $$
DECLARE
  sa_id INT;
BEGIN
  SELECT id INTO sa_id FROM subject_areas WHERE name = 'חבורות - זוהר מאור';

  INSERT INTO sub_disciplines (name, subject_area_id) VALUES
    ('חבורת אהבת חינם',    sa_id),
    ('חבורת ארץ ישראל',    sa_id),
    ('חבורת בוגרים',       sa_id),
    ('חבורת זהות',         sa_id),
    ('חבורת זוהר',         sa_id),
    ('חבורת יובל',         sa_id),
    ('חבורת כח',           sa_id),
    ('חבורת מגדר',         sa_id),
    ('חבורת מוסר',         sa_id),
    ('חבורת פנומנולוגית',  sa_id),
    ('חבורת פנימיות',      sa_id),
    ('חבורת שותים',        sa_id)
  ON CONFLICT (name) DO NOTHING;

  -- Link existing chavura recordings to the new sub-disciplines + subject area.
  -- The chavurot table has the same names as the new sub_disciplines rows,
  -- so we join through chavurot.name = sub_disciplines.name.
  UPDATE recordings r
  SET
    sub_discipline_id = sd.id,
    subject_area_id   = sa_id
  FROM chavurot c
  JOIN sub_disciplines sd
    ON sd.name = c.name
   AND sd.subject_area_id = sa_id
  WHERE r.chavura_id = c.id;

  RAISE NOTICE 'Updated % recordings', (
    SELECT COUNT(*) FROM recordings WHERE subject_area_id = sa_id
  );
END;
$$;
