-- =============================================================
-- SiachBot — Supabase Schema
-- Run this in the Supabase SQL editor (Project → SQL Editor → New query)
-- =============================================================

-- Reference tables (controlled vocabularies)

CREATE TABLE teachers (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  aliases TEXT[] DEFAULT '{}'
);

CREATE TABLE subject_areas (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE sub_disciplines (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  subject_area_id INT REFERENCES subject_areas(id)
);

CREATE TABLE series (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  teacher_id INT REFERENCES teachers(id),
  subject_area_id INT REFERENCES subject_areas(id),
  total_lessons INT
);

CREATE TABLE chavurot (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE studied_figures (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

-- Main table

CREATE TABLE recordings (
  id SERIAL PRIMARY KEY,
  message_id INT UNIQUE NOT NULL,
  date DATE,
  hebrew_date TEXT,
  semester TEXT,
  filename TEXT,
  title TEXT,
  teacher_id INT REFERENCES teachers(id),
  subject_area_id INT REFERENCES subject_areas(id),
  sub_discipline_id INT REFERENCES sub_disciplines(id),
  series_id INT REFERENCES series(id),
  lesson_number INT,
  chavura_id INT REFERENCES chavurot(id),
  is_oneoff BOOLEAN DEFAULT false,
  duration_seconds INT,
  file_size_bytes BIGINT,
  telegram_link TEXT,
  audio_downloaded BOOLEAN DEFAULT false,
  audio_r2_path TEXT,
  confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
  needs_human_review BOOLEAN DEFAULT false,
  tagged_by TEXT DEFAULT 'claude',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Many-to-many junction tables

CREATE TABLE recording_studied_figures (
  recording_id INT REFERENCES recordings(id) ON DELETE CASCADE,
  figure_id INT REFERENCES studied_figures(id),
  PRIMARY KEY (recording_id, figure_id)
);

CREATE TABLE recording_tags (
  recording_id INT REFERENCES recordings(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  PRIMARY KEY (recording_id, tag)
);

-- Indexes

CREATE INDEX ON recordings(teacher_id);
CREATE INDEX ON recordings(series_id);
CREATE INDEX ON recordings(subject_area_id);
CREATE INDEX ON recordings(confidence);
CREATE INDEX ON recordings(date DESC);
CREATE INDEX ON recordings(needs_human_review);
CREATE INDEX ON recordings USING gin(to_tsvector('simple', coalesce(title, '')));
