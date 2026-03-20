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

-- Subject areas with recording count
CREATE OR REPLACE FUNCTION subject_areas_with_count()
RETURNS TABLE(id INT, name TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT sa.id, sa.name, COUNT(r.id) AS count
  FROM subject_areas sa
  LEFT JOIN recordings r ON r.subject_area_id = sa.id
  GROUP BY sa.id
  ORDER BY count DESC, sa.name;
$$;

-- Sub-disciplines for a subject area with recording count
CREATE OR REPLACE FUNCTION sub_disciplines_with_count(p_subject_area_id INT)
RETURNS TABLE(id INT, name TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT sd.id, sd.name, COUNT(r.id) AS count
  FROM sub_disciplines sd
  LEFT JOIN recordings r ON r.sub_discipline_id = sd.id
  WHERE sd.subject_area_id = p_subject_area_id
  GROUP BY sd.id
  ORDER BY count DESC, sd.name;
$$;

-- Subject areas for a specific teacher (with count)
CREATE OR REPLACE FUNCTION subject_areas_by_teacher(p_teacher_id INT)
RETURNS TABLE(id INT, name TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT sa.id, sa.name, COUNT(r.id) AS count
  FROM subject_areas sa
  JOIN recordings r ON r.subject_area_id = sa.id
  WHERE r.teacher_id = p_teacher_id
  GROUP BY sa.id
  ORDER BY count DESC, sa.name;
$$;

-- Sub-disciplines for a teacher + subject area (with count)
CREATE OR REPLACE FUNCTION sub_disciplines_by_teacher_and_subject(p_teacher_id INT, p_subject_area_id INT)
RETURNS TABLE(id INT, name TEXT, count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT sd.id, sd.name, COUNT(r.id) AS count
  FROM sub_disciplines sd
  JOIN recordings r ON r.sub_discipline_id = sd.id
  WHERE r.teacher_id = p_teacher_id
    AND r.subject_area_id = p_subject_area_id
  GROUP BY sd.id
  ORDER BY count DESC, sd.name;
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
