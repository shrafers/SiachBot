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

## Project Stages

### Stage 1 — Scrape Metadata (no audio download yet)
Use Telethon to scrape ALL messages from the group. For every audio message, collect full context and save as raw JSON. Do NOT download audio files yet.

### Stage 2 — Analyze the Raw Data
Browse the JSON. Find patterns. Count recordings, identify duplicates, understand naming conventions before touching the database.

### Stage 3 — Tag with Claude API
Feed each recording's full context to Claude. Extract: rabbi, topic, series, lesson number, date. Save results back to JSON first — review manually before importing anywhere.

### Stage 4 — Design Database + Import
Design Supabase schema based on what Stage 2 revealed. Import tagged JSON into database.

### Stage 5 — Download Audio Files
Now that data is clean and deduplicated, download actual audio files to Cloudflare R2. Update database records with file paths.

### Stage 6 — Build the Bot
Build on top of clean data. Features: upload new lesson, search by rabbi/topic/series, browse by date.

---

## Critical: Message-to-Recording Linking

This is the most important scraping logic. For every audio file, collect ALL surrounding context — do not decide the label at scrape time, let Claude decide later.

**Known patterns:**
- Filename itself is descriptive: `הרב אלחנן - שותים - 28.5.25.m4a`
- Caption sent WITH the file: file + inline caption text
- Text message AFTER the file (same sender, <3 min): file → label
- Text message BEFORE the file (same sender, <3 min): label → file
- No label at all: filename only

**Every audio record must capture:**
```json
{
  "message_id": 12345,
  "date": "2025-09-03",
  "sender": "יאיר סט",
  "filename": "קול_014.m4a",
  "duration_seconds": 1638,
  "file_size_bytes": 14000000,
  "caption": "text sent with file, or null",
  "prev_message": {
    "text": "...",
    "sender": "...",
    "time_diff_seconds": 45
  },
  "next_message": {
    "text": "...",
    "sender": "...",
    "time_diff_seconds": 30
  },
  "telegram_link": "t.me/c/groupid/12345",
  "audio_downloaded": false,
  "audio_r2_path": null
}
```

Save one JSON file per message, plus one combined `all_recordings.json`.

---

## Database Schema (rough)

```
recordings
  id, message_id, telegram_link
  rabbi, topic, series, lesson_number
  date, duration_seconds
  audio_r2_path, filename_original
  tagged_by (claude/manual), confidence
  created_at
```

---

## Important Notes
- Scrape metadata first, audio files later (could be gigabytes)
- Always save raw JSON before touching the database — it's your safety net
- The Telegram group may close — eventually download everything
- Some recordings are uploaded by multiple members — deduplicate by duration + date + rabbi
- Language is Hebrew (RTL) — Claude API handles this well
- mark the stage that we are working on as in process, and done when done. commit after each process. 