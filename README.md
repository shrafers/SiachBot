# SiachBot

A Telegram bot for archiving, tagging, and searching yeshiva lesson recordings.

The group it was built for shares audio files (m4a/mp3) informally — inconsistent naming, no metadata, labels sometimes in a separate message. This project builds a full pipeline: scrape → tag with AI → store → serve via bot.

---

## What it does

- **Scrapes** audio message metadata from a Telegram group (no manual work)
- **Tags** every recording with Claude AI — extracting teacher, subject area, series, lesson number, studied figures, and free-form tags
- **Stores** structured metadata in Supabase (Postgres) and audio files in Cloudflare R2
- **Serves** a Hebrew-language Telegram bot with browse, search, and upload flows

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Telegram scraping | Telethon (userbot) |
| Telegram bot | python-telegram-bot |
| Database | Supabase (Postgres) |
| File storage | Cloudflare R2 (S3-compatible) |
| AI tagging | Anthropic Claude API (Batches API) |
| Hebrew date conversion | pyluach |
| Hosting | Railway.app |

---

## Pipeline stages

```
Stage 1 — Scrape metadata        ✅
Stage 2 — Analyze raw data       ✅
Stage 3 — Tag with Claude AI     ✅
Stage 4 — Design DB + import     ✅
Stage 5 — Download audio to R2   ✅
Stage 6a — Bot core              ✅
Stage 6b — Bot smart features    🔄
Stage 7 — Ongoing ingestion      ⬜
```

### Stage 1 — Scrape
`scrape.py` iterates all messages in the group using Telethon. For each audio message it collects:
- File metadata (name, size, duration)
- The message caption
- The text message immediately before and after (same sender, within 3 minutes) — context the teacher may have sent separately
- Hebrew and Gregorian dates

Output: one JSON file per message + a combined `all_recordings.json`.

### Stage 3 — AI Tagging
`tag_recordings.py` sends every recording through the Anthropic Batches API (50% cost reduction vs real-time). Each request includes the filename, caption, and surrounding message context.

Claude extracts:
- Teacher name
- Subject area and sub-discipline
- Series name and lesson number
- Studied figures (e.g. a shiur *about* Rav Kook is tagged separately from the teacher)
- Free-form tags
- Confidence level (`high` / `medium` / `low`)

### Stage 4 — Database
`schema.sql` + `import_to_supabase.py` build a normalized Postgres schema with reference tables for teachers, series, subject areas, sub-disciplines, and studied figures.

Key design decisions:
- Many-to-many for tags and studied figures
- Deduplication by `(date, teacher_id, duration ±60s)`
- `needs_human_review` flag for low-confidence or ambiguous records
- Postgres full-text search index on titles

### Stage 5 — Audio download
`download_to_r2.py` downloads audio files from Telegram via Telethon and uploads them to Cloudflare R2 at `audio/{year}/{message_id}.{ext}`. Runs in batches of 20, logs failures without crashing the full run.

---

## Bot features

The bot is fully in Hebrew and serves ~158 yeshiva members.

### Browse
- By teacher → subject area → sub-discipline → recordings
- By subject area → sub-disciplines → recordings
- By series → recordings ordered by lesson number
- Recently added (last 10)

### Search
Free-text search across title, teacher name, series name, sub-discipline, tags, and studied figures — backed by a Postgres RPC with ranked results.

### Result card
```
📖 Title
👤 Teacher  |  📚 Series — Lesson N  |  📅 Date
🏷 tag1, tag2
⏱ Duration
```
With inline buttons: Download | More like this | ◀ Prev  Next ▶

### Download
- If the file is in R2 → fetches and sends bytes directly
- Otherwise → sends the original Telegram link as fallback

### Upload flow
Step-by-step guided form for community members to contribute new recordings:
1. Teacher (from existing list or add new)
2. Subject area
3. Sub-discipline
4. Title (free text)
5. Series (existing / standalone / new)
6. Lesson number (optional)
7. Notes (optional)
8. Preview → confirm / edit / cancel

Uploaded files go to R2 and are flagged `needs_human_review = true`. Admin is notified automatically.

### Admin commands
- `/review` — work through the review queue one record at a time
- `/manage` — edit any record by ID
- `/stats` — usage statistics
- `/trust` — grant trusted-user status

---

## Project structure

```
scrape.py               # Stage 1 — metadata scraping
analyze_data.py         # Stage 2 — data exploration
tag_recordings.py       # Stage 3 — Claude AI tagging
import_to_supabase.py   # Stage 4 — DB import
download_to_r2.py       # Stage 5 — audio download pipeline
schema.sql              # Postgres schema
bot/
  __main__.py           # Entry point
  db.py                 # All DB queries
  r2.py                 # R2 upload/download helpers
  handlers/
    browse.py           # Browse flows
    search.py           # Search command
    upload.py           # Upload form
    results.py          # Result card rendering
    admin.py            # Admin commands
    callbacks.py        # Inline button router
```

---

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your credentials
python -m bot
```

Required environment variables (see `.env.example`):
- `TELEGRAM_BOT_TOKEN`
- `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, `TG_GROUP_ID` (Telethon userbot)
- `SUPABASE_URL`, `SUPABASE_KEY`
- `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`
- `ANTHROPIC_API_KEY`
- `ADMIN_CHAT_ID`

---

## Notes

- The Telethon userbot runs as a regular user account, not a bot — required to read group message history
- The bot is Hebrew-RTL throughout; all UI strings are in Hebrew
- `teacher` and `studied_figure` are always separate entities — a shiur *about* a figure by a different teacher is discoverable under both
- Low-confidence AI tags are never hidden — they show with a warning badge
