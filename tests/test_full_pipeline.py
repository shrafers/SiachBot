"""
test_full_pipeline.py — Minimal end-to-end bot: receive audio → download → upload to R2.

Run: python test_upload/test_full_pipeline.py

Send any audio/voice/document file to the bot. It will:
  1. Download the file using download_as_bytearray() (the correct method)
  2. Upload the bytes to R2 at audio/test/{message_id}.{ext}
  3. Reply with success (showing R2 path) or failure (showing which step broke)

No form, no DB, no URL hacking. This is the minimum viable chain.
If this works → the full upload flow can be fixed by replacing the download code.
If this fails → check which step fails and why.
"""

import asyncio
import io
import logging
import os
from datetime import datetime

import boto3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
LOCAL_SERVER = os.environ.get("TELEGRAM_LOCAL_SERVER")

REQUIRED_R2 = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]


def _make_r2():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _upload_r2(data: bytes, path: str) -> None:
    bucket = os.environ["R2_BUCKET_NAME"]
    _make_r2().put_object(Bucket=bucket, Key=path, Body=data)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    audio = msg.audio or msg.voice or msg.document
    if not audio:
        await msg.reply_text("Send an audio file, voice note, or document.")
        return

    file_id = audio.file_id
    filename = getattr(audio, "file_name", None) or "audio"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
    fake_id = int(datetime.now().timestamp())
    r2_path = f"audio/test/{fake_id}.{ext}"

    status = await msg.reply_text("⬛⬜⬜ Step 1/3: downloading from Telegram...")

    # Step 1: Download
    try:
        tg_file = await context.bot.get_file(file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        await status.edit_text(
            f"⬛⬛⬜ Step 2/3: uploading {len(audio_bytes):,} bytes to R2..."
        )
    except Exception as e:
        await status.edit_text(
            f"❌ FAILED at Step 1 (Telegram download)\n{type(e).__name__}: {e}"
        )
        return

    # Step 2: Upload to R2
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _upload_r2, audio_bytes, r2_path)
        await status.edit_text("⬛⬛⬛ Step 3/3: verifying R2 object...")
    except Exception as e:
        await status.edit_text(
            f"❌ FAILED at Step 2 (R2 upload)\n{type(e).__name__}: {e}"
        )
        return

    # Step 3: Verify (download back and check size)
    try:
        bucket = os.environ["R2_BUCKET_NAME"]
        buf = io.BytesIO()
        loop = asyncio.get_event_loop()
        s3 = _make_r2()
        await loop.run_in_executor(None, lambda: s3.download_fileobj(bucket, r2_path, buf))
        verified_size = len(buf.getvalue())
        await status.edit_text(
            f"✅ Full pipeline works!\n\n"
            f"File: {filename}\n"
            f"Size: {len(audio_bytes):,} bytes\n"
            f"R2 path: {r2_path}\n"
            f"Verified: {verified_size:,} bytes read back from R2\n\n"
            f"The fix is: replace the URL-hacking download in upload.py with:\n"
            f"  audio_bytes = bytes(await tg_file.download_as_bytearray())"
        )
    except Exception as e:
        await status.edit_text(
            f"⚠️ Upload succeeded but verification failed\n"
            f"R2 path: {r2_path}\n"
            f"Verify error: {type(e).__name__}: {e}"
        )


def main() -> None:
    missing = [k for k in REQUIRED_R2 if not os.environ.get(k)]
    if missing:
        print(f"ERROR: missing env vars: {missing}")
        return

    builder = Application.builder().token(TOKEN)
    if LOCAL_SERVER:
        print(f"Using local server: {LOCAL_SERVER}")
        builder = (
            builder
            .local_mode(True)
            .base_url(f"{LOCAL_SERVER}/bot")
            .base_file_url(f"{LOCAL_SERVER}/file/bot")
        )
    else:
        print("Using official Telegram API (no local server)")

    app = builder.build()
    AUDIO_FILTER = filters.AUDIO | filters.VOICE | filters.Document.ALL
    app.add_handler(MessageHandler(AUDIO_FILTER, handle_file))
    print("Pipeline test bot running. Send an audio file.")
    app.run_polling()


if __name__ == "__main__":
    main()
