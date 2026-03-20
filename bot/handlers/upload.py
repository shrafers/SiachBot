"""Upload handler — receive audio, collect metadata via form, insert into DB."""

import io
import os
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, Message
from telegram.ext import ContextTypes

from .. import db, r2
from ..keyboards import confirm_upload_keyboard, back_to_main

load_dotenv()

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

# ---------------------------------------------------------------------------
# Form steps — mandatory first, then optional
# ---------------------------------------------------------------------------

STEPS = [
    # (key, label, mandatory)
    ("teacher",        "שם המוסר שיעור",                                True),
    ("subject_area",   "תחום (הלכה / גמרא / פנימיות / מוסר / ...)",    True),
    ("sub_discipline", "תת-תחום (לדוגמה: בבא קמא / תפילה / ...)",      True),
    ("series_name",    "שם הסדרה (או 'דלג' אם שיעור בודד)",            False),
    ("lesson_number",  "מספר שיעור בסדרה (או 'דלג')",                  False),
    ("notes",          "הערות נוספות (או 'דלג')",                        False),
]

MANDATORY_KEYS = {k for k, _, m in STEPS if m}


# ---------------------------------------------------------------------------
# Entry point: audio message received
# ---------------------------------------------------------------------------

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg: Message = update.message

    # Detect forward from the original group
    forward_origin = msg.forward_origin
    if forward_origin and hasattr(forward_origin, "message_id"):
        original_message_id = forward_origin.message_id
        existing = db.get_recording_by_message_id(original_message_id)
        if existing:
            from ..utils import format_result_card
            card = format_result_card(existing)
            await msg.reply_text(
                f"השיעור הזה כבר קיים בארכיון:\n\n{card}",
                parse_mode="Markdown",
                reply_markup=back_to_main(),
            )
            return

    audio = msg.audio or msg.voice or msg.document
    if not audio:
        await msg.reply_text("שלח קובץ שמע (mp3/m4a/ogg).")
        return

    filename = getattr(audio, "file_name", None) or "audio"
    caption = msg.caption or ""

    context.user_data["upload"] = {
        "file_id": audio.file_id,
        "filename": filename,
        "caption": caption,
        "file_size": getattr(audio, "file_size", None),
        "duration": getattr(audio, "duration", None),
        "form": {},
        "step": 0,
    }
    context.user_data["awaiting"] = "upload_form"

    await _ask_step(msg, context)


# ---------------------------------------------------------------------------
# Step-by-step form
# ---------------------------------------------------------------------------

async def _ask_step(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["upload"]
    step = state["step"]

    if step >= len(STEPS):
        await _show_preview(msg, context)
        return

    _, label, mandatory = STEPS[step]
    suffix = "" if mandatory else " (אופציונלי — שלח 'דלג' לדילוג)"
    await msg.reply_text(f"{'*' if mandatory else ''}📝 {label}{suffix}{'*' if mandatory else ''}:")


async def handle_form_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        return

    msg = update.message
    text = msg.text.strip()
    step = state["step"]
    key, label, mandatory = STEPS[step]

    if text.lower() in ("דלג", "skip"):
        if mandatory:
            await msg.reply_text(f"⚠️ שדה זה חובה. אנא הזן {label}:")
            return
        state["form"][key] = None
    else:
        if key == "lesson_number":
            state["form"][key] = int(text) if text.isdigit() else None
        else:
            state["form"][key] = text

    state["step"] += 1
    await _ask_step(msg, context)


async def _show_preview(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["upload"]
    form = state["form"]

    preview = _format_preview(form, state["filename"])
    await msg.reply_text(
        f"📋 *סיכום השיעור:*\n\n{preview}\n\nהאם לשמור?",
        parse_mode="Markdown",
        reply_markup=confirm_upload_keyboard(),
    )


# ---------------------------------------------------------------------------
# Confirm / edit / cancel (called from callbacks.py)
# ---------------------------------------------------------------------------

async def confirm_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer("אין העלאה פעילה.")
        return

    # Validate mandatory fields
    form = state["form"]
    missing = [label for key, label, mandatory in STEPS if mandatory and not form.get(key)]
    if missing:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "⚠️ חסרים שדות חובה:\n" + "\n".join(f"• {l}" for l in missing)
        )
        return

    await update.callback_query.answer()
    msg = update.callback_query.message
    await msg.reply_text("מעלה לארכיון... ⏳")

    file_id = state["file_id"]
    filename = state["filename"]

    # Download from Telegram
    tg_file = await update.callback_query.get_bot().get_file(file_id)
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"
    year = datetime.now().year
    fake_message_id = int(datetime.now().timestamp())
    r2_path = f"audio/{year}/{fake_message_id}.{ext}"

    await r2.upload_audio(audio_bytes, r2_path)

    row = {
        "message_id": fake_message_id,
        "title": form.get("series_name") or form.get("teacher"),
        "filename": filename,
        "audio_downloaded": True,
        "audio_r2_path": r2_path,
        "needs_human_review": True,
        "tagged_by": "manual-upload",
        "duration_seconds": state.get("duration"),
        "file_size_bytes": state.get("file_size"),
    }

    lesson_num = form.get("lesson_number")
    if isinstance(lesson_num, int):
        row["lesson_number"] = lesson_num

    notes = form.get("notes")
    if notes:
        row["title"] = f"{row['title']} — {notes}" if row.get("title") else notes

    db.insert_new_recording(row)

    # Notify admin
    try:
        preview = _format_preview(form, filename)
        await update.callback_query.get_bot().send_message(
            ADMIN_CHAT_ID,
            f"📥 שיעור חדש הועלה לבדיקה:\n\n{preview}",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    context.user_data.pop("upload", None)
    context.user_data.pop("awaiting", None)
    await msg.reply_text(
        "✅ השיעור נשמר בהצלחה! הוא יוצג לאחר אישור המנהל.",
        reply_markup=back_to_main(),
    )


async def restart_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-start the form from step 0 (edit flow)."""
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer("אין העלאה פעילה.")
        return
    state["step"] = 0
    state["form"] = {}
    context.user_data["awaiting"] = "upload_form"
    await update.callback_query.answer()
    await _ask_step(update.callback_query.message, context)


async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("upload", None)
    context.user_data.pop("awaiting", None)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("בוטל ❌", reply_markup=back_to_main())


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _format_preview(form: dict, filename: str = "") -> str:
    lines = []
    if form.get("teacher"):
        lines.append(f"👤 {form['teacher']}")
    if form.get("subject_area"):
        lines.append(f"📂 {form['subject_area']}")
    if form.get("sub_discipline"):
        lines.append(f"📋 {form['sub_discipline']}")
    series = form.get("series_name")
    lesson = form.get("lesson_number")
    if series:
        s = f"📚 {series}"
        if lesson:
            s += f" — שיעור {lesson}"
        lines.append(s)
    if form.get("notes"):
        lines.append(f"📝 {form['notes']}")
    if filename:
        lines.append(f"📁 {filename}")
    return "\n".join(lines) if lines else "(אין פרטים)"
