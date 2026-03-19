# Yeshiva Lessons Telegram Bot

## Project Goal
Scrape, organize, and serve yeshiva lesson recordings from a Telegram group.
The group has 158 members and contains audio recordings (m4a/mp3) shared informally — inconsistent naming, no tagging, labels sometimes in separate messages.

## Tech Stack
- **Language**: Python
- **Telegram scraping**: Telethon (userbot, not bot API)
- **Database**: Supabase (Postgres)
- **File storage**: Cloudflare R2 (audio files)
- **Bot**: python-telegram-bot
- **Hosting**: Railway.app
- **LLM tagging**: Anthropic Claude API
- **Search**: Postgres full-text search (no external search engine needed)

---

## Stages Overview

| Stage | Name | Status |
|-------|------|--------|
| 1 | Scrape metadata | ✅ Done |
| 2 | Analyze raw data | ✅ Done |
| 3 | Tag with Claude API | ✅ Done |
| 4 | Design DB + Import | 🔄 In Progress |
| 5 | Download audio files | ⬜ Pending |
| 6a | Bot core | ⬜ Pending |
| 6b | Bot smart features | ⬜ Pending |
| 7 | Ongoing ingestion | ⬜ Pending |

---

## Stage 4 — Design Database + Import 🔄 IN PROGRESS

### Goal
Design a Supabase schema that serves the bot's search and browse needs, then import tagged_recordings.json. The schema must reflect all facets the bot will query — do not design it as a flat dump.

### Schema

```sql
-- Reference tables (controlled vocabularies — insert unique values from JSON first)
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

-- Many-to-many
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
```

### Required Indexes
```sql
CREATE INDEX ON recordings(teacher_id);
CREATE INDEX ON recordings(series_id);
CREATE INDEX ON recordings(subject_area_id);
CREATE INDEX ON recordings(confidence);
CREATE INDEX ON recordings(date DESC);
CREATE INDEX ON recordings(needs_human_review);
CREATE INDEX ON recordings USING gin(to_tsvector('simple', coalesce(title, '')));
```

### Import Steps
1. Load `tagged_recordings.json`
2. Collect all unique values → insert reference tables first (teachers, subject_areas, sub_disciplines, series, chavurot, studied_figures)
3. Insert recordings with foreign key lookups
4. Insert many-to-many rows (recording_studied_figures, recording_tags)
5. Deduplication: flag recordings with same `(date, teacher_id)` and `duration_seconds` within ±60s — set `needs_human_review = true` on the duplicate
6. Validation: any recording with null title AND null teacher → set `needs_human_review = true`

### Commit when done
`git commit -m "stage4: supabase schema + import from tagged JSON"`

---

## Stage 5 — Download Audio Files ⬜ PENDING

### Goal
Download all audio files from Telegram to Cloudflare R2. Update DB records.

### Steps
1. Query: `SELECT * FROM recordings WHERE audio_downloaded = false ORDER BY confidence DESC`
2. For each: download via Telethon using message_id
3. Upload to R2 at path: `audio/{year}/{message_id}.{ext}`
4. Update: `audio_r2_path`, `audio_downloaded = true`
5. Run in batches of 20 — log failures, never crash the full run

### Commit when done
`git commit -m "stage5: audio downloaded to R2"`

---

## Stage 6a — Bot Core ⬜ PENDING

### Goal
A working Telegram bot: browse, search, download, and upload lessons.

### Commands
- `/start` — main menu
- `/search [text]` — free text search
- `/series` — browse series index
- `/teacher` — browse teachers list
- `/upload` — upload a new lesson

### Main Menu (inline keyboard)
```
🔍 חיפוש     📚 עיון לפי מרצה
📖 סדרות     🕐 אחרונים
⬆️ העלאת שיעור
```

### Browse Flow
- By teacher → sorted by recording count descending → tap teacher → list their recordings
- By subject area → 8 areas → tap area → sub-disciplines (only those with 5+ recordings; rest under "אחר") → results
- By chavura → list of chavurot → results

### Search Logic (no AI call — use Postgres)
Query across: title, series name, teacher name, sub_discipline name, studied_figures, tags.
Use `to_tsvector('simple', ...)` for Hebrew full-text. Also do substring match on teacher name.

Ranking order:
1. Exact series name match
2. Exact teacher name match
3. Title full-text match
4. Tag / studied figure match
5. Fuzzy / partial match

High-confidence results rank above low-confidence at each tier.

After results appear, show quick filter buttons:
`הכל` | `סדרות בלבד` | `שיעורים בודדים`

### Result Card Format
```
📖 כותרת השיעור
👤 מרצה  |  📚 סדרה — שיעור X  |  📅 תאריך
🏷 תג1, תג2
```
Buttons: `⬇ הורדה` | `עוד כמו זה` | `◀ הקודם  הבא ▶` (series only)

Show `⚠️ מידע לא מאומת` label under cards with `confidence = 'low'`.

Pagination: 3–5 results per page with `→ הבא` / `← הקודם` buttons.

### Download
When user taps ⬇ הורדה:
- If `audio_r2_path` exists → send the file from R2
- If not yet downloaded → reply: "הקובץ עדיין לא הורד, שלח לינק טלגרם" + `telegram_link`

### Upload Flow (new lesson)
1. User sends audio file (or forwards from group) to bot, optionally with a caption
2. Bot replies: "מעבד..." — calls Claude API with filename + caption to extract: title, teacher, subject, series, lesson_number
3. Bot shows extracted metadata as a preview:
   ```
   📖 [כותרת]
   👤 [מרצה]  |  📚 [סדרה — שיעור X]
   ✅ אשר   ✏️ ערוך   ❌ בטל
   ```
4. On ✅ confirm: upload audio to R2 → insert into DB with `confidence = 'medium'`, `needs_human_review = true` → notify ADMIN_CHAT_ID
5. On ✏️ edit: bot asks user to correct each field one by one, then confirm
6. On ❌ cancel: discard

### Commit when done
`git commit -m "stage6a: bot core — browse, search, download, upload"`

---

## Stage 6b — Bot Smart Features ⬜ PENDING

### Goal
Layer discovery and quality tools on top of the working core.

### Features

**עוד כמו זה button:**
Query by strongest shared facet in order: same series → same teacher + subject → same studied figure. Return a fresh result page.

**Series navigation:**
When displaying a result that belongs to a series, always show `◀ הקודם  הבא ▶` buttons. On the series index page, show total lessons and flag missing numbers: `⚠️ חסרים שיעורים: 4, 7`.

**Admin review queue:**
`/review` command (admin only, checks ADMIN_CHAT_ID). Shows one `needs_human_review = true` record at a time with buttons: `✅ אשר` | `✏️ ערוך` | `⏭ דלג`. On approve: sets `needs_human_review = false`.

**Recently added:**
Main menu `🕐 אחרונים` → last 10 records by `created_at DESC`.

### Commit when done
`git commit -m "stage6b: smart features — discovery, series gaps, review queue"`

---

## Stage 7 — Ongoing Ingestion ⬜ PENDING

### Goal
Keep the archive growing as new lessons are shared in the group.

### Steps
1. Telethon watcher (or scheduled poll every N hours) monitors the group for new audio messages
2. For each new audio: collect prev/next message context → call Claude API to tag
3. Auto-insert with `needs_human_review = true` if confidence < high
4. Notify admin via bot

### Commit when done
`git commit -m "stage7: ongoing ingestion pipeline"`

---

## Critical: Message-to-Recording Linking

For every audio, collect ALL surrounding context. Never decide the label at scrape time — let Claude decide in Stage 3.

**Known patterns:**
- Descriptive filename: `הרב אלחנן - שותים - 28.5.25.m4a`
- Caption sent with the file
- Text message after the file (same sender, <3 min)
- Text message before the file (same sender, <3 min)
- No label: filename only

---

## Important Rules
- Always keep raw JSON as backup before any DB operation
- `teacher` and `studied_figure` are always separate — a shiur about הרב קוק by זוהר מאור must be findable under both
- Low-confidence items are never hidden — they show with a warning badge and rank lower
- Deduplication key: `(date, teacher_id, duration_seconds ±60s)`
- ADMIN_CHAT_ID must be set in env — used for upload notifications and /review queue
- Mark stages in this file as 🔄 or ✅ as you go. Commit after every stage.