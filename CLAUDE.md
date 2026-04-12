# SiachBot — Technical Reference

## What this project is

A Telegram bot that archives, tags, and serves yeshiva lesson recordings from a private Telegram group (~158 members). Audio files (m4a/mp3) are shared informally with inconsistent naming. The project:
1. Scraped all historical messages with Telethon
2. Tagged each recording with Claude AI (teacher, series, lesson number, studied figures, tags)
3. Imported structured data into Supabase (Postgres)
4. Downloaded audio to Cloudflare R2
5. Runs a Hebrew-language Telegram bot for browse, search, upload, and admin

All pipeline stages (1–6) are complete. Stage 7 (ongoing auto-ingestion) is not yet built.

---

## Tech stack

| Concern | Technology |
|---------|-----------|
| Language | Python 3.12 |
| Telegram bot | python-telegram-bot |
| Telegram scraping / large downloads | Telethon (userbot) |
| Database | Supabase (Postgres) |
| File storage | Cloudflare R2 (S3-compatible) |
| AI tagging | Anthropic Claude API (Batches API) |
| Hebrew calendar | pyluach |
| Hosting | Railway.app |

---

## Directory structure

```
bot/                        # Running Telegram bot — Python package
  __main__.py               # Entry point: python -m bot
  db.py                     # ONLY place that touches Supabase
  r2.py                     # R2 upload/download/presigned URLs
  telethon_client.py        # MTProto client for large file downloads (no 20MB limit)
  cost_report.py            # Monthly cost email; called by job queue in __main__.py
  keyboards.py              # All inline/reply keyboard builders
  utils.py                  # encode_cb/decode_cb, format_result_card, format_duration
  assets/
    thanks_image.png        # Image sent as sticker after upload confirm
  handlers/
    __init__.py
    start.py                # /start, /help — registers user in bot_users
    search.py               # /search flow — free text → DB RPC → paginated results
    browse.py               # Browse by teacher / series / year / chavura
    results.py              # Shared helper: render paginated recording list
    upload.py               # Multi-step upload form → R2 + DB insert
    admin.py                # /review, /manage, /trust, /stats (admin + trusted users)
    callbacks.py            # Central router for ALL inline button callbacks

scripts/                    # One-time and pipeline scripts (run from project root)
  scrape.py                 # Stage 1
  tag_recordings.py         # Stage 3 — Claude Batches API
  import_to_supabase.py     # Stage 4 — JSON → DB
  download_to_r2.py         # Stage 5 — Telegram → R2
  add_hebrew_dates.py       # Enrich tagged JSON with Hebrew calendar fields
  backfill_hebrew_year.py   # One-time DB column backfill
  backfill_file_sizes.py    # One-time DB column backfill
  apply_series_assignments.py  # Apply manual CSV series assignments to DB
  build_review_html.py      # Generate interactive HTML to organize series
  analyze_data.py           # Print stats from tagged JSON
  export_lists.py           # Export lists to data/full_lists.txt
  list_groups.py            # Utility: find Telegram group ID
  run_sql.py                # Utility: run SQL from stdin via psycopg2

data/                       # Data files — not committed if large
  all_recordings.json       # Raw scraped metadata (Stage 1 output)
  tagged_recordings.json    # AI-tagged output (Stage 3 output, source for Stage 4)
  recordings/               # One JSON per message (Stage 1)

migrations/                 # Supabase SQL migrations — applied in order
  01_enable_trgm.sql
  02_search_text.sql
  03_stats_tables.sql
  add_hebrew_year.sql

sql/                        # Reference SQL — not migrations, not auto-applied
  schema.sql                # Full schema DDL reference
  supabase_rpc.sql          # RPC function definitions
  add_chavurot_subject.sql  # Ad-hoc migration

prompts/
  tag_recordings.txt        # System prompt for Claude AI tagging (Stage 3)

tests/                      # Manual test scripts

siachbot.session            # Telethon session file — always run scripts from root
```

---

## Database schema

### Core tables

**`recordings`** — main table, one row per lesson
- `id`, `message_id` (unique — Telegram message ID)
- `title`, `filename`, `date`, `hebrew_date`, `hebrew_year`, `semester`
- `teacher_id` → teachers
- `series_id` → series, `lesson_number`
- `chavura_id` → chavurot
- `duration_seconds`, `file_size_bytes`
- `audio_downloaded` (bool), `audio_r2_path` (e.g. `audio/2024/12345.m4a`)
- `telegram_link` (fallback if not in R2)
- `needs_human_review` (bool) — set true for low-confidence, duplicates, manual uploads
- `deleted_at` (soft delete)
- `tagged_by` — `'claude'` or `'manual-upload'`
- `created_at`

**`teachers`** — `id`, `name`

**`series`** — `id`, `name`, `teacher_id`

**`chavurot`** — `id`, `name` (learning groups)

**`studied_figures`** — `id`, `name` (historical/rabbinic figures a shiur is *about*)

### Junction tables
- **`recording_tags`** — `(recording_id, tag)` — free-form tags
- **`recording_studied_figures`** — `(recording_id, figure_id)` — many-to-many

### Tracking tables
- **`trusted_users`** — `telegram_user_id`, `added_by`, `added_at`
- **`bot_users`** — `user_id`, `username`, `first_seen`, `last_seen`
- **`user_events`** — `user_id`, `event_type`, `event_data`, `created_at`

### RPC functions (Supabase)
Called via `supabase.rpc(...)` in `db.py`:
- `teachers_with_count` — teachers sorted by recording count
- `series_chronological` / `series_by_teacher_chrono` — series with lesson counts
- `chavurot_with_count`
- `hebrew_years_with_count`, `zmanim_by_year_with_count`
- `get_all_stats`, `top_downloaded_recordings`, `top_search_queries`

> **Note:** `subject_areas` and `sub_disciplines` columns exist in the DB from earlier schema versions but are no longer exposed in the bot UI or upload form. Browse and upload use only: teacher, series, chavura, year/semester.

---

## Bot architecture

### Entry point: `bot/__main__.py`
- Registers all command handlers, audio handler, text router, and callback handler
- `_text_router` dispatches free-text messages based on `context.user_data["awaiting"]`
- Monthly job: `cost_report.run_cost_report()` via job queue (1st of month, 08:00 UTC)

### Database layer: `bot/db.py`
Single access point for all Supabase queries. Key patterns:
- Singletons: `get_supabase()` cached per process
- `_flatten_joins(rec)` — converts Supabase nested join dicts to flat keys (e.g. `teachers.name` → `teacher_name`)
- Trusted user list cached in-memory with 60s TTL
- `PAGE_SIZE = 5` (recording lists), `LIST_SIZE = 10` (teacher/series browse lists)

### Callback routing: `bot/handlers/callbacks.py`
All inline button presses go through `handle_callback()`. Callback data is compact JSON encoded by `utils.encode_cb()` / `utils.decode_cb()` (must fit Telegram's 64-byte limit). Routes by `action` key:
- Browse: `browse_teachers`, `teacher_recs`, `browse_series`, `series_recs`, `browse_chav`, `browse_zmanim`, `zman_year`, `zman_recs`, `recent`
- Search: `search_page`, `search_filter`
- Download: `dl` → fetch from R2 (bytes if ≤20MB, presigned URL if >20MB) or Telegram link
- Like: `like` → same series → same teacher → same studied figure (fallback chain)
- Upload form: `up_tea*`, `up_ser*`, `up_skip`, `up_confirm`, `up_edit`, `up_cancel`
- Admin: `rev_ok`, `rev_skip`, `rev_edit`, `manage`, `mg_*`

### Browse flows: `bot/handlers/browse.py`
- **By teacher** → teacher list (sorted by count) → teacher's series + "standalone" option → recordings
- **By series** → all series (chronological) → recordings by lesson_number
- **By year (zman)** → Hebrew years → semesters (אלול/חורף/קיץ) → recordings
- **By chavura** → chavura list → recordings
- **Recent** → last 10 by `created_at DESC`

All lists are paginated using `LIST_SIZE`. All recording pages paginated using `PAGE_SIZE`.

### Upload flow: `bot/handlers/upload.py`
State machine stored in `context.user_data["upload"]`. Steps:
1. `teacher` (buttons — common teachers + "others" + "new")
2. `title` (free text, mandatory)
3. `series` (buttons — teacher's series + "standalone" + "new")
4. `lesson_number` (free text, optional; auto-skipped if no series chosen)
5. `notes` (free text, optional)
6. Preview → confirm → download from Telegram via Telethon → upload to R2 → insert DB row

On confirm:
- Generates a fake `message_id` from timestamp
- R2 path: `audio/{year}/{fake_message_id}.{ext}`
- Inserts with `needs_human_review = False` (trusted user upload)
- Notifies `ADMIN_CHAT_ID`
- Posts audio to `CHANNEL_ID` if set
- Sends a WebP sticker from `bot/assets/thanks_image.png`

Forwarded files are checked by `message_id` — if found in DB, shows existing record.

### Admin: `bot/handlers/admin.py`
- `is_admin(user_id)` — checks `ADMIN_CHAT_ID` env var
- `is_trusted(user_id)` — admin OR in `trusted_users` table (cached 60s)
- `/review` — shows next `needs_human_review=true` record; approve/skip/edit
- `/manage <id>` — change series, teacher, title, or soft-delete a recording
- `/stats` — calls `db.get_stats()` → renders dashboard with user counts, top downloads, top searches
- `/trust list|add|remove` — manage trusted users

---

## Key patterns and rules

**Running scripts:** Always run from the project root (`python scripts/scrape.py`, not `cd scripts && python scrape.py`). Scripts use CWD-relative paths for `data/` references. `siachbot.session` is resolved from CWD.

**`teacher` vs `studied_figure`:** These are always separate. A shiur *about* Rav Kook taught by Zohar Maor must be findable under both. Never conflate them.

**Deduplication key:** `(date, teacher_id, duration_seconds ±60s)` — duplicates get `needs_human_review = true`.

**`needs_human_review`:** Set true for: low-confidence AI tags, duplicates, manual uploads (via upload form), and records with null title + null teacher. Low-confidence items are never hidden from users — they display normally.

**Soft delete:** `deleted_at` timestamp on `recordings`. DB queries filter `deleted_at IS NULL`.

**R2 downloads:** Files ≤20MB → send bytes directly via bot API. Files >20MB → generate 1-hour presigned URL and send as link. Local Telegram Bot API server (docker-compose) bypasses the 20MB limit entirely.

**Callback data size:** Telegram enforces a 64-byte limit on callback data. `encode_cb()` in `utils.py` packs action + params as compact JSON and raises if over limit.

**Telethon client:** `bot/telethon_client.py` uses `TELEGRAM_BOT_TOKEN` to connect as a bot via MTProto (not the bot API). This allows downloading files larger than 20MB. Session is lazily initialized and auto-reconnects.

---

## Environment variables

```
# Telegram bot
TELEGRAM_BOT_TOKEN
ADMIN_CHAT_ID
ADMIN_USERNAME
CHANNEL_ID          # channel to auto-post new uploads (optional)
CHANNEL_LINK        # shown in /help

# Telethon userbot (scraping + large downloads)
TG_API_ID
TG_API_HASH
TG_PHONE
TG_GROUP_ID

# Supabase
SUPABASE_URL
SUPABASE_KEY
DATABASE_URL        # direct Postgres URL (for psycopg2 in run_sql.py)

# Cloudflare R2
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME

# Anthropic (only needed for scripts/tag_recordings.py)
ANTHROPIC_API_KEY

# Cost report email
GMAIL_SENDER
GMAIL_APP_PASSWORD
REPORT_EMAIL
CF_API_TOKEN        # Cloudflare API token for R2 usage stats

# Fixed monthly costs for report
RAILWAY_MONTHLY_COST
SUPABASE_MONTHLY_COST

# Local Telegram Bot API server (optional, docker-compose)
TELEGRAM_LOCAL_SERVER
```
