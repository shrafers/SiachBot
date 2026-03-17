"""
Stage 1: Scrape metadata for all audio messages in the Telegram group.
No audio files are downloaded — metadata and context only.

Output:
  data/recordings/<message_id>.json  — one file per audio message
  data/all_recordings.json           — combined list of all records
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]
GROUP_ID = int(os.environ["TG_GROUP_ID"])

DATA_DIR = Path("data/recordings")
ALL_RECORDINGS_PATH = Path("data/all_recordings.json")

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".oga", ".opus"}
CONTEXT_WINDOW_SECONDS = 180  # 3 minutes


def is_audio_message(msg) -> bool:
    if msg is None or msg.media is None:
        return False
    doc = getattr(msg.media, "document", None)
    if doc is None:
        return False
    mime = getattr(doc, "mime_type", "") or ""
    if mime.startswith("audio/"):
        return True
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            ext = Path(attr.file_name).suffix.lower()
            if ext in AUDIO_EXTENSIONS:
                return True
    return False


def get_sender_name(sender) -> str:
    if sender is None:
        return "unknown"
    first = getattr(sender, "first_name", "") or ""
    last = getattr(sender, "last_name", "") or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    return str(getattr(sender, "id", "unknown"))


def get_filename(doc) -> str | None:
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
    return None


def get_duration(doc) -> int | None:
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeAudio):
            return attr.duration
    return None


def build_context_message(msg, audio_date, sender_name: str) -> dict | None:
    if msg is None or msg.text is None or msg.text.strip() == "":
        return None
    diff = abs((msg.date - audio_date).total_seconds())
    if diff > CONTEXT_WINDOW_SECONDS:
        return None
    return {
        "text": msg.text,
        "sender": sender_name,
        "time_diff_seconds": int(diff),
    }


def make_telegram_link(group_id: int, message_id: int) -> str:
    # Strip the -100 prefix that Telethon uses for supergroups/channels
    clean_id = str(group_id)
    if clean_id.startswith("-100"):
        clean_id = clean_id[4:]
    elif clean_id.startswith("-"):
        clean_id = clean_id[1:]
    return f"t.me/c/{clean_id}/{message_id}"


async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with TelegramClient("siachbot", API_ID, API_HASH) as client:
        await client.start(phone=PHONE)

        print(f"Fetching all messages from group {GROUP_ID}...")
        messages = []
        async for msg in client.iter_messages(GROUP_ID, limit=None):
            messages.append(msg)

        # iter_messages returns newest-first; reverse to chronological order
        messages.reverse()
        print(f"Total messages fetched: {len(messages)}")

        # Build a lookup: message_id -> index for fast neighbor access
        id_to_index = {msg.id: i for i, msg in enumerate(messages)}

        # Load sender info in bulk
        await client.get_participants(GROUP_ID)

        recordings = []
        skipped = 0
        found = 0
        sender_cache: dict[int, str] = {}  # sender_id -> display name

        async def get_sender_name_cached(sender_id) -> str:
            if sender_id is None:
                return "unknown"
            if sender_id in sender_cache:
                return sender_cache[sender_id]
            for _ in range(3):
                try:
                    entity = await client.get_entity(sender_id)
                    name = get_sender_name(entity)
                    sender_cache[sender_id] = name
                    return name
                except FloodWaitError as e:
                    print(f"  [rate limit] Telegram asks to wait {e.seconds}s — sleeping...")
                    await asyncio.sleep(e.seconds + 2)
                except Exception:
                    break
            sender_cache[sender_id] = f"user_{sender_id}"
            return sender_cache[sender_id]

        for i, msg in enumerate(messages):
            if not is_audio_message(msg):
                continue

            out_path = DATA_DIR / f"{msg.id}.json"
            if out_path.exists():
                print(f"  [skip] {msg.id} already scraped")
                skipped += 1
                # Still load it into recordings list
                with open(out_path, encoding="utf-8") as f:
                    recordings.append(json.load(f))
                continue

            doc = msg.media.document
            filename = get_filename(doc)
            duration = get_duration(doc)
            file_size = doc.size

            # Sender — cached so we only call get_entity once per unique user
            sender_name = await get_sender_name_cached(msg.sender_id)

            # Caption = text on the audio message itself
            caption = msg.text.strip() if msg.text and msg.text.strip() else None

            # Prev message context — same sender, within 3 min
            prev_msg = messages[i - 1] if i > 0 else None
            prev_context = None
            if prev_msg and prev_msg.text and prev_msg.sender_id == msg.sender_id:
                prev_context = build_context_message(prev_msg, msg.date, sender_name)

            # Next message context — same sender, within 3 min
            next_msg = messages[i + 1] if i < len(messages) - 1 else None
            next_context = None
            if next_msg and next_msg.text and next_msg.sender_id == msg.sender_id:
                next_context = build_context_message(next_msg, msg.date, sender_name)

            record = {
                "message_id": msg.id,
                "date": msg.date.strftime("%Y-%m-%d"),
                "sender": sender_name,
                "filename": filename,
                "duration_seconds": duration,
                "file_size_bytes": file_size,
                "caption": caption,
                "prev_message": prev_context,
                "next_message": next_context,
                "telegram_link": make_telegram_link(GROUP_ID, msg.id),
                "audio_downloaded": False,
                "audio_r2_path": None,
            }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            recordings.append(record)
            found += 1
            print(f"  [{found}] Saved message {msg.id} — {filename}")

        # Write combined file
        with open(ALL_RECORDINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(recordings, f, ensure_ascii=False, indent=2)

        print(f"\nDone.")
        print(f"  New recordings scraped : {found}")
        print(f"  Previously scraped     : {skipped}")
        print(f"  Total in all_recordings: {len(recordings)}")
        print(f"  Output: {ALL_RECORDINGS_PATH}")


asyncio.run(main())
