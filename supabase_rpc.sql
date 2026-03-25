-- RPC functions needed by the bot (run in Supabase SQL editor)

-- Teachers with recording count
CREATE OR REPLACE FUNCTION teachers_with_count()
RETURNS TABLE(id INT, name TEXT, aliases TEXT[], count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT t.id, t.name, t.aliases, COUNT(r.id) AS count
  FROM teachers t
  LEFT JOIN recordings r ON r.teacher_id = t.id
  GROUP BY t.id
  ORDER BY count DESC, t.name;
$$;

-- Series for a specific teacher ordered by most recent lesson date
CREATE OR REPLACE FUNCTION series_by_teacher_chrono(p_teacher_id INT)
RETURNS TABLE(id INT, name TEXT, total_lessons INT, last_date DATE)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, s.total_lessons, MAX(r.date) AS last_date
  FROM series s
  LEFT JOIN recordings r ON r.series_id = s.id
  WHERE s.teacher_id = p_teacher_id
  GROUP BY s.id, s.name, s.total_lessons
  ORDER BY last_date DESC NULLS LAST;
$$;

-- All series ordered by most recent lesson date (all-series chronological browse)
CREATE OR REPLACE FUNCTION series_chronological(p_offset INT DEFAULT 0, p_limit INT DEFAULT 10)
RETURNS TABLE(id INT, name TEXT, teacher_name TEXT, lesson_count BIGINT, last_date DATE)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, t.name AS teacher_name, COUNT(r.id) AS lesson_count, MAX(r.date) AS last_date
  FROM series s
  LEFT JOIN teachers t ON t.id = s.teacher_id
  LEFT JOIN recordings r ON r.series_id = s.id
  GROUP BY s.id, s.name, t.name
  ORDER BY last_date DESC NULLS LAST
  LIMIT p_limit OFFSET p_offset;
$$;

-- Chavurot with recording count
CREATE OR REPLACE FUNCTION chavurot_with_count()
RETURNS TABLE(id INT, name TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT c.id, c.name, COUNT(r.id) AS count
  FROM chavurot c
  LEFT JOIN recordings r ON r.chavura_id = c.id
  GROUP BY c.id
  ORDER BY count DESC, c.name;
$$;

-- Hebrew years with recording count (sorted by most recent date first)
CREATE OR REPLACE FUNCTION hebrew_years_with_count()
RETURNS TABLE(hebrew_year TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT hebrew_year, COUNT(id) AS count
  FROM recordings
  WHERE hebrew_year IS NOT NULL
  GROUP BY hebrew_year
  ORDER BY MAX(date) DESC;
$$;

-- Semesters for a given Hebrew year with recording count
CREATE OR REPLACE FUNCTION zmanim_by_year_with_count(p_year TEXT)
RETURNS TABLE(semester TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT semester, COUNT(id) AS count
  FROM recordings
  WHERE hebrew_year = p_year AND semester IS NOT NULL
  GROUP BY semester
  ORDER BY count DESC;
$$;
