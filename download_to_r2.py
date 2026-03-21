"""
Stage 5 — Download audio files from Telegram and upload to Cloudflare R2.

Prerequisites:
  - schema.sql applied and import_to_supabase.py already run (recordings in DB)
  - R2 bucket created; R2_* vars set in .env
  - Telethon session file (siachbot.session) present

Usage:
  pip install boto3
  python download_to_r2.py
"""

import asyncio
import io
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from supabase import create_client, Client
from telethon import TelegramClient
from telethon.errors import FloodWaitError

load_dotenv()

# Telegram
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]
GROUP_ID = int(os.environ["TG_GROUP_ID"])

# Supabase
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# R2
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET = os.environ["R2_BUCKET_NAME"]

BATCH_SIZE = 20
SLEEP_BETWEEN_FILES = 1  # seconds


def make_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def get_extension(filename: str | None) -> str:
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".m4a", ".mp3", ".ogg", ".opus", ".oga"}:
            return ext
    return ".m4a"


def r2_path(date: str | None, message_id: int, ext: str) -> str:
    year = date[:4] if date else "unknown"
    return f"audio/{year}/{message_id}{ext}"


async def download_one(client: TelegramClient, s3, sb: Client, rec: dict, index: int, total: int) -> bool:
    message_id = rec["message_id"]
    prefix = f"[{index}/{total}] msg={message_id}"

    # Fetch message
    try:
        msg = await client.get_messages(GROUP_ID, ids=message_id)
    except FloodWaitError as e:
        print(f"  {prefix} FloodWait {e.seconds}s — sleeping...")
        await asyncio.sleep(e.seconds + 2)
        try:
            msg = await client.get_messages(GROUP_ID, ids=message_id)
        except Exception as ex:
            print(f"  {prefix} ERROR re-fetching after flood wait: {ex}")
            return False

    if msg is None or not msg.media:
        print(f"  {prefix} SKIP — no media found")
        return False

    # Download to memory
    try:
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        buf.seek(0)
        data = buf.read()
    except FloodWaitError as e:
        print(f"  {prefix} FloodWait {e.seconds}s during download — sleeping...")
        await asyncio.sleep(e.seconds + 2)
        return False
    except Exception as e:
        print(f"  {prefix} ERROR downloading: {e}")
        return False

    # Determine R2 path
    ext = get_extension(rec.get("filename"))
    path = r2_path(rec.get("date"), message_id, ext)
    size_mb = len(data) / 1_048_576

    # Upload to R2
    try:
        s3.put_object(Bucket=R2_BUCKET, Key=path, Body=data)
    except (BotoCoreError, ClientError) as e:
        print(f"  {prefix} ERROR uploading to R2: {e}")
        return False

    # Update DB
    try:
        sb.table("recordings").update({
            "audio_r2_path": path,
            "audio_downloaded": True,
            "file_size_bytes": len(data),
        }).eq("message_id", message_id).execute()
    except Exception as e:
        print(f"  {prefix} ERROR updating DB: {e}")
        # File is in R2 but DB not updated — next run will re-upload (idempotent)
        return False

    print(f"  {prefix} → {path} ({size_mb:.1f} MB)")
    return True


async def main():
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    s3 = make_s3_client()

    # Fetch all pending recordings, sort high confidence first
    print("Fetching pending recordings from Supabase...")
    result = (
        sb.table("recordings")
        .select("message_id, date, filename, confidence")
        .eq("audio_downloaded", False)
        .execute()
    )
    conf_order = {"high": 0, "medium": 1, "low": 2}
    pending = sorted(result.data, key=lambda r: conf_order.get(r.get("confidence", "low"), 2))
    total = len(pending)
    print(f"  {total} recordings to download.\n")

    if total == 0:
        print("Nothing to do.")
        return

    succeeded = 0
    failed = 0
    skipped = 0

    async with TelegramClient("siachbot", API_ID, API_HASH) as tg:
        await tg.start(phone=PHONE)

        for i, rec in enumerate(pending, start=1):
            # Process in logical batches (log batch boundary)
            if (i - 1) % BATCH_SIZE == 0:
                batch_num = (i - 1) // BATCH_SIZE + 1
                total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
                print(f"\n--- Batch {batch_num}/{total_batches} ---")

            result = await download_one(tg, s3, sb, rec, i, total)
            if result is True:
                succeeded += 1
            elif result is False:
                # distinguish skip vs error by checking if msg had media
                failed += 1

            if i < total:
                await asyncio.sleep(SLEEP_BETWEEN_FILES)

    print(f"\n=== Done ===")
    print(f"  Succeeded : {succeeded}")
    print(f"  Failed    : {failed}")
    print(f"  Total     : {total}")


if __name__ == "__main__":
    asyncio.run(main())
