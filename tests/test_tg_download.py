"""
test_tg_download.py — Diagnostic bot to understand exactly what happens when
the bot tries to download a file that a user uploaded to Telegram.

Run: python test_upload/test_tg_download.py

Send any audio/voice/document file to the bot. It will:
  - Print the raw file_path returned by get_file()
  - Try 3 download methods and report size or error for each

This has ZERO side effects: no R2, no DB, no form. Pure diagnosis.

Method 1: tg_file.download_as_bytearray()        <- idiomatic, should always work
Method 2: httpx GET on tg_file.file_path          <- current buggy approach
Method 3: manually constructed local server URL    <- only if TELEGRAM_LOCAL_SERVER is set
"""

import asyncio
import io
import logging
import os

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
LOCAL_SERVER = os.environ.get("TELEGRAM_LOCAL_SERVER")
WORK_DIR = os.environ.get("TELEGRAM_WORK_DIR", "/var/lib/telegram-bot-api")


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    audio = msg.audio or msg.voice or msg.document
    if not audio:
        await msg.reply_text("Send an audio file, voice note, or document.")
        return

    file_id = audio.file_id
    filename = getattr(audio, "file_name", "audio") or "audio"
    file_size = getattr(audio, "file_size", None)

    lines = [
        f"📁 File received: {filename}",
        f"   file_id: {file_id}",
        f"   file_size: {file_size} bytes",
        f"   LOCAL_SERVER env: {LOCAL_SERVER or '(not set — using official API)'}",
        "",
    ]
    await msg.reply_text("\n".join(lines))

    # --- get_file() ---
    status = await msg.reply_text("Calling get_file()...")
    try:
        tg_file = await context.bot.get_file(file_id)
        raw_path = tg_file.file_path
        await status.edit_text(
            f"get_file() succeeded.\n\nraw file_path:\n{raw_path}"
        )
    except Exception as e:
        await status.edit_text(f"❌ get_file() FAILED:\n{type(e).__name__}: {e}")
        return

    # --- Method 1: download_as_bytearray() ---
    m1 = await msg.reply_text("Method 1: download_as_bytearray()...")
    try:
        data = bytes(await tg_file.download_as_bytearray())
        await m1.edit_text(
            f"Method 1 ✅ download_as_bytearray()\n  → {len(data)} bytes downloaded"
        )
    except Exception as e:
        await m1.edit_text(
            f"Method 1 ❌ download_as_bytearray()\n  → {type(e).__name__}: {e}"
        )

    # --- Method 2: httpx GET on raw file_path (current approach) ---
    m2 = await msg.reply_text("Method 2: httpx GET on file_path...")
    try:
        import re
        url = re.sub(r'(?<![:/])//+', '/', raw_path)
        url = url.replace(f"{WORK_DIR}/{TOKEN}/", "/")
        logger.info("Method 2 constructed URL: %s", url)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            await m2.edit_text(
                f"Method 2 ✅ httpx GET\n  URL: {url}\n  → {len(resp.content)} bytes"
            )
    except Exception as e:
        await m2.edit_text(
            f"Method 2 ❌ httpx GET\n  URL: {url if 'url' in dir() else '(not constructed)'}\n  → {type(e).__name__}: {e}"
        )

    # --- Method 3: manually constructed local server URL (only if LOCAL_SERVER is set) ---
    if LOCAL_SERVER:
        m3 = await msg.reply_text("Method 3: manual local server URL...")
        try:
            # The local server stores files at {WORK_DIR}/{TOKEN}/{relative_path}
            # It serves them at {LOCAL_SERVER}/file/bot{TOKEN}/{relative_path}
            # raw_path from local server is: {WORK_DIR}/{TOKEN}/{relative_path} (absolute disk path)
            prefix = f"{WORK_DIR}/{TOKEN}/"
            if raw_path.startswith(prefix):
                relative = raw_path[len(prefix):]
            elif WORK_DIR in raw_path:
                # It's been embedded in a URL already
                import re
                m = re.search(rf"{re.escape(WORK_DIR)}/{re.escape(TOKEN)}/(.*)", raw_path)
                relative = m.group(1) if m else raw_path
            else:
                relative = raw_path.lstrip("/")

            url3 = f"{LOCAL_SERVER}/file/bot{TOKEN}/{relative}"
            logger.info("Method 3 constructed URL: %s", url3)
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url3)
                resp.raise_for_status()
                await m3.edit_text(
                    f"Method 3 ✅ manual local URL\n  URL: {url3}\n  → {len(resp.content)} bytes"
                )
        except Exception as e:
            await m3.edit_text(
                f"Method 3 ❌ manual local URL\n  URL: {url3 if 'url3' in dir() else '(error)'}\n  → {type(e).__name__}: {e}"
            )
    else:
        await msg.reply_text("Method 3: skipped (TELEGRAM_LOCAL_SERVER not set)")

    await msg.reply_text("--- Diagnosis complete. Check results above. ---")


def main() -> None:
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
    print("Diagnostic bot running. Send an audio file.")
    app.run_polling()


if __name__ == "__main__":
    main()
