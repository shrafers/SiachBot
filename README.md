# SiachBot

A Telegram bot for archiving, tagging, and searching yeshiva lesson recordings.

The group it was built for shares audio files (m4a/mp3) informally — inconsistent naming, no metadata, labels sometimes in a separate message. This project builds a full pipeline: scrape → tag with AI → store → serve via bot.

---

## What it does

- **Scrapes** audio message metadata from a Telegram group (no manual work)
- **Tags** every recording with Claude AI — extracting teacher, series, lesson number, studied figures, and free-form tags
- **Stores** structured metadata in Supabase (Postgres) and audio files in Cloudflare R2
- **Serves** a Hebrew-language Telegram bot with browse, search, upload, and admin flows

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Telegram scraping | Telethon (userbot) |
| Telegram bot | python-telegram-bot |
| Database | Supabase (Postgres) |
| File storage | Cloudflare R2 (S3-compatible) |
| AI tagging | Anthropic Claude API (Batches API) |
| Hebrew dates | pyluach |
| Hosting | Railway.app |

---

## Project structure

```
bot/                        # The running Telegram bot (Python package)
  __main__.py               # Entry point — run with: python -m bot
  db.py                     # All database queries (single access point)
  r2.py                     # Cloudflare R2 upload/download
  telethon_client.py        # MTProto client for large file downloads
  cost_report.py            # Monthly cost email (called by job queue)
  keyboards.py              # All inline/reply keyboard builders
  utils.py                  # Formatting helpers, callback encode/decode
  assets/
    thanks_image.png        # Sticker sent after successful upload
  handlers/
    start.py                # /start, /help
    search.py               # /search flow
    browse.py               # Browse by teacher / series / year / chavura
    results.py              # Paginated result card rendering
    upload.py               # Audio upload form
    admin.py                # /review, /manage, /trust, /stats
    callbacks.py            # Central inline button router

scripts/                    # One-time and pipeline scripts (run from project root)
  scrape.py                 # Stage 1 — scrape message metadata from Telegram
  tag_recordings.py         # Stage 3 — tag with Claude Batches API
  import_to_supabase.py     # Stage 4 — import tagged JSON into DB
  download_to_r2.py         # Stage 5 — download audio from Telegram to R2
  add_hebrew_dates.py       # Add Hebrew date fields to tagged JSON
  backfill_hebrew_year.py   # One-time DB backfill
  backfill_file_sizes.py    # One-time DB backfill
  apply_series_assignments.py  # Apply manual series CSV to DB
  build_review_html.py      # Generate HTML review tool
  analyze_data.py           # Statistics from tagged JSON
  export_lists.py           # Export lists to txt
  list_groups.py            # Find Telegram group ID
  run_sql.py                # Execute SQL from stdin

data/                       # Raw and processed JSON data files
  all_recordings.json       # Combined metadata from scrape
  tagged_recordings.json    # AI-tagged output (source of truth before DB)
  recordings/               # One JSON per message from Stage 1

migrations/                 # Supabase SQL migrations (applied in order)

sql/                        # Reference SQL — schema definition and RPC functions
  schema.sql
  supabase_rpc.sql
  add_chavurot_subject.sql

prompts/
  tag_recordings.txt        # System prompt used by tag_recordings.py

tests/                      # Test scripts
```

---

## Pipeline (already run — for reference)

```
Stage 1 — Scrape metadata        ✅  scripts/scrape.py
Stage 2 — Analyze raw data       ✅  scripts/analyze_data.py
Stage 3 — Tag with Claude AI     ✅  scripts/tag_recordings.py
Stage 4 — Import to DB           ✅  scripts/import_to_supabase.py
Stage 5 — Download audio to R2   ✅  scripts/download_to_r2.py
Stage 6 — Bot                    ✅  bot/
Stage 7 — Ongoing ingestion      ⬜  not yet built
```

**Stage 1 — Scrape:** Telethon iterates all group messages. For each audio it captures the filename, size, duration, caption, and the text messages immediately before/after (same sender, within 3 min). Output: `data/recordings/<id>.json` + `data/all_recordings.json`.

**Stage 3 — AI Tagging:** Each recording is sent to the Anthropic Batches API (50% cheaper than real-time). Claude extracts teacher, series, lesson number, studied figures, tags, and a confidence level (`high/medium/low`). Prompt is in `prompts/tag_recordings.txt`.

**Stage 4 — DB import:** `scripts/import_to_supabase.py` reads `data/tagged_recordings.json`, resolves entity IDs, and inserts into all tables. Deduplication key: `(date, teacher_id, duration_seconds ±60s)`.

**Stage 5 — Audio:** Downloads via Telethon, uploads to R2 at `audio/{year}/{message_id}.{ext}`, updates `audio_r2_path` and `audio_downloaded` in DB.

---

## Bot features

The bot is fully in Hebrew and serves ~158 yeshiva members.

### Browse
- By teacher → teacher's series → recordings
- By series → all series → recordings ordered by lesson number
- By year (zman) → semester → recordings
- By chavura → recordings
- Recently added (last 10)

### Search
Free-text search across title, teacher name, series name, tags, and studied figures — backed by a Postgres RPC with ranked results (date DESC). Filter buttons: all | series only | standalone.

### Result card
```
📖 Title
👤 Teacher  |  📚 Series — Lesson N  |  📅 Date
🏷 tag1, tag2
⏱ Duration  #id
```
Inline buttons: Download | More like this | ◀ Prev  Next ▶

### Download
- If in R2 and ≤20MB → fetches bytes, sends directly
- If in R2 and >20MB → sends a presigned URL (1hr)
- If not in R2 → sends the original Telegram link as fallback

### Upload flow
Community members contribute recordings via a guided form:
1. Teacher (from list or add new)
2. Title (free text, mandatory)
3. Series (existing / standalone / new, optional)
4. Lesson number (optional, auto-skipped if no series)
5. Notes (optional)
6. Preview → confirm / edit / cancel

Forwarded files from the original group are checked against the DB by `message_id` — if already archived, the existing record is shown instead of re-uploading. On confirm: file goes to R2, record inserted with `needs_human_review = true`, admin notified.

### Admin commands
- `/review` — work through the review queue one record at a time (approve / edit / skip)
- `/manage <id>` — edit any record: change series, teacher, title, or soft-delete
- `/stats` — usage dashboard (users, archive size, top downloads, top searches)
- `/trust` — grant or revoke trusted-user status

---

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
python -m bot
```

Key environment variables (see `.env.example`):
- `TELEGRAM_BOT_TOKEN`
- `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, `TG_GROUP_ID` (Telethon userbot)
- `SUPABASE_URL`, `SUPABASE_KEY`
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- `ANTHROPIC_API_KEY`
- `ADMIN_CHAT_ID`

For large file downloads (>20MB bot API limit), a local Telegram Bot API server can be run via `docker-compose up`.

---

## Notes

- The Telethon userbot runs as a regular user account, not a bot — required to read group message history. `siachbot.session` in the project root holds the Telethon session; always run scripts from the project root.
- All UI strings are in Hebrew (RTL).
- `teacher` and `studied_figure` are always separate entities — a shiur *about* a figure by a different teacher is findable under both.
- Low-confidence AI tags are never hidden — they show with a warning badge.
- Scripts in `scripts/` use CWD-relative paths for `data/`; always run them from the project root.
