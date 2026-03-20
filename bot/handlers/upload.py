"""Upload handler — receive audio, tag with Claude, confirm, insert into DB."""

import io
import json
import os
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from telegram import Update, Message
from telegram.ext import ContextTypes

from .. import db, r2
from ..keyboards import confirm_upload_keyboard, back_to_main
from ..utils import format_result_card

load_dotenv()

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

_anthropic = anthropic.Anthropic()

# Fields collected during edit flow, in order
EDIT_FIELDS = ["title", "teacher", "subject_area", "series_name", "lesson_number"]
EDIT_LABELS = {
    "title": "כותרת השיעור",
    "teacher": "שם המוסר",
    "subject_area": "תחום (הלכה / גמרא / פנימיות / ...)",
    "series_name": "שם הסדרה (או 'בודד')",
    "lesson_number": "מספר השיעור בסדרה (או 'לא ידוע')",
}


# ---------------------------------------------------------------------------
# Entry point: audio message received
# ---------------------------------------------------------------------------

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg: Message = update.message

    # Detect if forwarded from the original group
    forward_origin = msg.forward_origin
    if forward_origin and hasattr(forward_origin, "message_id"):
        original_message_id = forward_origin.message_id
        existing = db.get_recording_by_message_id(original_message_id)
        if existing:
            card = format_result_card(existing)
            await msg.reply_text(
                f"השיעור הזה כבר קיים בארכיון:\n\n{card}",
                parse_mode="Markdown",
                reply_markup=back_to_main(),
            )
            return

    # New audio — tag with Claude
    audio = msg.audio or msg.voice or msg.document
    if not audio:
        await msg.reply_text("שלח קובץ שמע (mp3/m4a/ogg).")
        return

    filename = getattr(audio, "file_name", None) or "audio"
    caption = msg.caption or ""

    processing_msg = await msg.reply_text("מעבד את השיעור... ⏳")

    try:
        metadata = await _tag_with_claude(filename, caption)
    except Exception as e:
        await processing_msg.edit_text(f"שגיאה בעיבוד: {e}")
        return

    # Store state
    context.user_data["upload"] = {
        "file_id": audio.file_id,
        "filename": filename,
        "caption": caption,
        "file_size": getattr(audio, "file_size", None),
        "duration": getattr(audio, "duration", None),
        "metadata": metadata,
        "edit_field_idx": 0,
    }

    await processing_msg.delete()
    preview = _format_upload_preview(metadata)
    await msg.reply_text(
        f"📋 *פרטי השיעור שזוהו:*\n\n{preview}",
        parse_mode="Markdown",
        reply_markup=confirm_upload_keyboard(),
    )


# ---------------------------------------------------------------------------
# Claude tagging
# ---------------------------------------------------------------------------

async def _tag_with_claude(filename: str, caption: str) -> dict:
    import asyncio

    def call():
        resp = _anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=(
                "You are a metadata extractor for yeshiva lesson recordings. "
                "Return ONLY valid JSON with these fields: "
                "title (string), teacher (string or null), subject_area (string or null), "
                "series_name (string or null), lesson_number (int or null), "
                "thematic_tags (array of strings). "
                "All values should be in Hebrew where applicable."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Filename: {filename}\n"
                    f"Caption: {caption or '(none)'}\n"
                    "Extract metadata."
                ),
            }],
        )
        text = resp.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call)


# ---------------------------------------------------------------------------
# Confirm / edit / cancel callbacks (called from callbacks.py)
# ---------------------------------------------------------------------------

async def confirm_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer("אין העלאה פעילה.")
        return

    await update.callback_query.answer()
    msg = update.callback_query.message
    await msg.reply_text("מעלה לארכיון... ⏳")

    file_id = state["file_id"]
    filename = state["filename"]
    metadata = state["metadata"]

    # Download from Telegram
    tg_file = await update.callback_query.get_bot().get_file(file_id)
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    # Determine extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"
    year = datetime.now().year

    # We don't have a real message_id for user-uploaded content — use a timestamp-based placeholder
    fake_message_id = int(datetime.now().timestamp())
    r2_path = f"audio/{year}/{fake_message_id}.{ext}"

    await r2.upload_audio(audio_bytes, r2_path)

    # Resolve FK ids best-effort (teacher by name lookup)
    row = {
        "message_id": fake_message_id,
        "title": metadata.get("title"),
        "filename": filename,
        "audio_downloaded": True,
        "audio_r2_path": r2_path,
        "confidence": "medium",
        "needs_human_review": True,
        "tagged_by": "claude-upload",
        "duration_seconds": state.get("duration"),
        "file_size_bytes": state.get("file_size"),
    }

    lesson_num = metadata.get("lesson_number")
    if isinstance(lesson_num, int):
        row["lesson_number"] = lesson_num

    inserted = db.insert_new_recording(row)

    tags = metadata.get("thematic_tags") or []
    if tags and inserted.get("id"):
        db.insert_recording_tags(inserted["id"], tags)

    # Notify admin
    try:
        preview = _format_upload_preview(metadata)
        await update.callback_query.get_bot().send_message(
            ADMIN_CHAT_ID,
            f"📥 שיעור חדש הועלה לבדיקה:\n\n{preview}",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    context.user_data.pop("upload", None)
    await msg.reply_text(
        "✅ השיעור נשמר בהצלחה! הוא יוצג לאחר אישור המנהל.",
        reply_markup=back_to_main(),
    )


async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer("אין העלאה פעילה.")
        return
    state["edit_field_idx"] = 0
    context.user_data["awaiting"] = "upload_edit"
    await update.callback_query.answer()
    field = EDIT_FIELDS[0]
    current = state["metadata"].get(field, "")
    await update.callback_query.message.reply_text(
        f"✏️ {EDIT_LABELS[field]}\nנוכחי: {current or '—'}\nהקלד ערך חדש (או 'דלג'):"
    )


async def handle_edit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        return

    idx = state.get("edit_field_idx", 0)
    field = EDIT_FIELDS[idx]
    text = update.message.text.strip()

    if text != "דלג":
        if field == "lesson_number":
            state["metadata"][field] = int(text) if text.isdigit() else None
        else:
            state["metadata"][field] = text

    idx += 1
    state["edit_field_idx"] = idx

    if idx >= len(EDIT_FIELDS):
        context.user_data.pop("awaiting", None)
        preview = _format_upload_preview(state["metadata"])
        await update.message.reply_text(
            f"📋 *פרטים מעודכנים:*\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=confirm_upload_keyboard(),
        )
    else:
        next_field = EDIT_FIELDS[idx]
        current = state["metadata"].get(next_field, "")
        await update.message.reply_text(
            f"✏️ {EDIT_LABELS[next_field]}\nנוכחי: {current or '—'}\nהקלד ערך חדש (או 'דלג'):"
        )


async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("upload", None)
    context.user_data.pop("awaiting", None)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("בוטל ❌", reply_markup=back_to_main())


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _format_upload_preview(metadata: dict) -> str:
    lines = []
    if metadata.get("title"):
        lines.append(f"📖 {metadata['title']}")
    if metadata.get("teacher"):
        lines.append(f"👤 {metadata['teacher']}")
    if metadata.get("subject_area"):
        lines.append(f"📂 {metadata['subject_area']}")
    series = metadata.get("series_name")
    lesson = metadata.get("lesson_number")
    if series:
        s = f"📚 {series}"
        if lesson:
            s += f" — שיעור {lesson}"
        lines.append(s)
    tags = metadata.get("thematic_tags") or []
    if tags:
        lines.append("🏷 " + ", ".join(tags[:5]))
    return "\n".join(lines) if lines else "(אין פרטים)"
