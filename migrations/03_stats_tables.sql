-- Migration 03: user tracking + event log for /stats command

-- Every unique Telegram user who ever interacts with the bot
CREATE TABLE IF NOT EXISTS bot_users (
    user_id    BIGINT PRIMARY KEY,
    username   TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lightweight event log
-- event_data examples:
--   download: {"recording_id": 42}
--   search:   {"query": "שבת", "results_count": 7}
--   upload:   {"recording_id": 99, "teacher": "הרב X"}
--   start:    {}
CREATE TABLE IF NOT EXISTS user_events (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('start','search','download','upload','browse')),
    event_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_events_type_created ON user_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events (user_id);
CREATE INDEX IF NOT EXISTS idx_bot_users_first_seen ON bot_users (first_seen DESC);

-- RPC: top downloaded recordings in a period
CREATE OR REPLACE FUNCTION top_downloaded_recordings(p_since TIMESTAMPTZ, p_limit INT)
RETURNS TABLE(recording_id INT, title TEXT, teacher_name TEXT, dl_count BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT
        (e.event_data->>'recording_id')::int AS recording_id,
        r.title,
        t.name AS teacher_name,
        COUNT(*) AS dl_count
    FROM user_events e
    LEFT JOIN recordings r ON r.id = (e.event_data->>'recording_id')::int
    LEFT JOIN teachers t   ON t.id = r.teacher_id
    WHERE e.event_type = 'download'
      AND e.created_at >= p_since
      AND e.event_data->>'recording_id' IS NOT NULL
    GROUP BY (e.event_data->>'recording_id')::int, r.title, t.name
    ORDER BY COUNT(*) DESC
    LIMIT p_limit;
$$;

-- RPC: top search queries in a period
CREATE OR REPLACE FUNCTION top_search_queries(p_since TIMESTAMPTZ, p_limit INT)
RETURNS TABLE(query TEXT, search_count BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT
        event_data->>'query' AS query,
        COUNT(*) AS search_count
    FROM user_events
    WHERE event_type = 'search'
      AND created_at >= p_since
      AND event_data->>'query' IS NOT NULL
      AND event_data->>'query' <> ''
    GROUP BY event_data->>'query'
    ORDER BY COUNT(*) DESC
    LIMIT p_limit;
$$;
