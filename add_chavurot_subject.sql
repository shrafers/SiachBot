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
END;
$$;
