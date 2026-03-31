"""Upload handler — receive audio, collect metadata via buttons+form, insert into DB."""

import io
import os
from datetime import datetime, date

from dotenv import load_dotenv
from pyluach import dates as hebdates
from telegram import Update, Message
from telegram.ext import ContextTypes

from .. import db, r2
from ..keyboards import (
    confirm_upload_keyboard,
    back_to_main,
    upload_teacher_keyboard,
    upload_teacher_other_keyboard,
    upload_series_keyboard,
    upload_skip_keyboard,
)

load_dotenv()

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
GROUP_CHAT_ID = int(os.environ.get("GROUP_CHAT_ID", "0"))  # channel/group to auto-post new lessons

# A celebration GIF (Giphy CDN — publicly accessible animation)
UPLOAD_SUCCESS_GIF = "https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif"

# Threshold for "common" teachers
TEACHER_THRESHOLD = 10

# ---------------------------------------------------------------------------
# Form steps
# input_mode: 'buttons' | 'text'
# mandatory: if False, skip button is shown; step can be skipped
# ---------------------------------------------------------------------------

STEPS = [
    # key             label                                  mandatory  input_mode
    ("teacher",        "בחר מוסר שיעור:",                    True,      "buttons"),
    ("title",          "כותרת השיעור:",                       True,      "text"),
    ("series",         "בחר סדרה:",                          False,     "buttons"),
    ("lesson_number",  "מספר שיעור בסדרה:",                  False,     "text"),
    ("notes",          "הערות נוספות:",                       False,     "text"),
]

MANDATORY_KEYS = {step[0] for step in STEPS if step[2]}


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
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
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
# Step router
# ---------------------------------------------------------------------------

async def _ask_step(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["upload"]
    step = state["step"]

    # Skip lesson_number if no series was selected
    if step < len(STEPS) and STEPS[step][0] == "lesson_number":
        if not state["form"].get("series_name"):
            state["step"] += 1
            step = state["step"]

    if step >= len(STEPS):
        await _show_preview(msg, context)
        return

    key, label, mandatory, input_mode = STEPS[step]

    if input_mode == "buttons":
        if key == "teacher":
            await _ask_teacher(msg, context)
        elif key == "series":
            await _ask_series(msg, context)
    else:
        # Text step — show skip button for optional ones
        if mandatory:
            await msg.reply_text(f"📝 {label}")
        else:
            await msg.reply_text(f"📝 {label}", reply_markup=upload_skip_keyboard())


# ---------------------------------------------------------------------------
# Button-based step prompts
# ---------------------------------------------------------------------------

async def _ask_teacher(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    all_teachers = db.get_teacher_list()
    main = [t for t in all_teachers if (t.get("count") or 0) >= TEACHER_THRESHOLD]
    others = [t for t in all_teachers if (t.get("count") or 0) < TEACHER_THRESHOLD]
    await msg.reply_text(
        "👤 *בחר מוסר שיעור:*",
        parse_mode="Markdown",
        reply_markup=upload_teacher_keyboard(main, has_others=bool(others)),
    )


async def _ask_series(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["upload"]
    teacher_id = state["form"].get("teacher_id")
    series = db.get_series_by_teacher(teacher_id) if teacher_id else []
    await msg.reply_text(
        "📚 *בחר סדרה:*",
        parse_mode="Markdown",
        reply_markup=upload_series_keyboard(series),
    )


# ---------------------------------------------------------------------------
# Callback handlers — teacher
# ---------------------------------------------------------------------------

async def handle_teacher_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, teacher_id: int) -> None:
    all_teachers = db.get_teacher_list()
    teacher = next((t for t in all_teachers if t["id"] == teacher_id), None)
    if not teacher:
        await update.callback_query.answer("מרצה לא נמצא.")
        return
    state = context.user_data["upload"]
    state["form"]["teacher"] = teacher["name"]
    state["form"]["teacher_id"] = teacher_id
    state["step"] += 1
    await update.callback_query.answer()
    await _ask_step(update.callback_query.message, context)


async def handle_teacher_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    all_teachers = db.get_teacher_list()
    others = [t for t in all_teachers if (t.get("count") or 0) < TEACHER_THRESHOLD]
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "👤 *מרצים נוספים:*",
        parse_mode="Markdown",
        reply_markup=upload_teacher_other_keyboard(others),
    )


async def handle_teacher_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await _ask_teacher(update.callback_query.message, context)


async def handle_teacher_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data["awaiting"] = "upload_new_teacher"
    await update.callback_query.message.reply_text("✏️ הקלד שם המרצה החדש:")


async def handle_new_teacher_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        return
    name = update.message.text.strip()
    state["form"]["teacher"] = name
    state["form"]["teacher_id"] = None
    state["step"] += 1
    context.user_data["awaiting"] = "upload_form"
    await _ask_step(update.message, context)


# ---------------------------------------------------------------------------
# Callback handlers — series
# ---------------------------------------------------------------------------

async def handle_series_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, series_id: int) -> None:
    state = context.user_data["upload"]
    teacher_id = state["form"].get("teacher_id")
    series_list = db.get_series_by_teacher(teacher_id) if teacher_id else []
    series = next((s for s in series_list if s["id"] == series_id), None)
    if not series:
        await update.callback_query.answer("סדרה לא נמצאה.")
        return
    state["form"]["series_name"] = series["name"]
    state["form"]["series_id"] = series_id
    state["step"] += 1
    await update.callback_query.answer()
    await _ask_step(update.callback_query.message, context)


async def handle_series_standalone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User chose 'standalone lesson' — skip series and lesson_number."""
    state = context.user_data["upload"]
    state["form"]["series_name"] = None
    state["form"]["series_id"] = None
    # Advance past series AND lesson_number steps
    state["step"] += 2
    await update.callback_query.answer()
    await _ask_step(update.callback_query.message, context)


async def handle_series_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data["awaiting"] = "upload_new_series"
    await update.callback_query.message.reply_text("✏️ הקלד שם הסדרה החדשה:")


async def handle_new_series_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        return
    name = update.message.text.strip()
    state["form"]["series_name"] = name
    state["form"]["series_id"] = None
    state["step"] += 1
    context.user_data["awaiting"] = "upload_form"
    await _ask_step(update.message, context)


# ---------------------------------------------------------------------------
# Skip handler (optional text steps)
# ---------------------------------------------------------------------------

async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer()
        return
    step = state["step"]
    if step < len(STEPS):
        key = STEPS[step][0]
        state["form"][key] = None
    state["step"] += 1
    await update.callback_query.answer()
    await _ask_step(update.callback_query.message, context)


# ---------------------------------------------------------------------------
# Text form handler (mandatory title + optional text steps)
# ---------------------------------------------------------------------------

async def handle_form_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        return

    msg = update.message
    text = msg.text.strip()
    step = state["step"]
    key = STEPS[step][0]

    if key == "lesson_number":
        state["form"][key] = int(text) if text.isdigit() else None
    else:
        state["form"][key] = text

    state["step"] += 1
    await _ask_step(msg, context)


# ---------------------------------------------------------------------------
# Hebrew date helpers (mirrors add_hebrew_dates.py logic)
# ---------------------------------------------------------------------------

_HEBREW_DIGITS = {
    1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה", 6: "ו", 7: "ז", 8: "ח", 9: "ט",
    10: "י", 11: "יא", 12: "יב", 13: "יג", 14: "יד", 15: "טו", 16: "טז",
    17: "יז", 18: "יח", 19: "יט", 20: "כ", 21: "כא", 22: "כב", 23: "כג",
    24: "כד", 25: "כה", 26: "כו", 27: "כז", 28: "כח", 29: "כט", 30: "ל",
}
_HEBREW_MONTHS = {
    1: "ניסן", 2: "אייר", 3: "סיון", 4: "תמוז", 5: "אב", 6: "אלול",
    7: "תשרי", 8: "חשוון", 9: "כסלו", 10: "טבת", 11: "שבט", 12: "אדר", 13: "אדר ב׳",
}


def _hebrew_date_str(hdate) -> str:
    day = _HEBREW_DIGITS.get(hdate.day, str(hdate.day))
    month = _HEBREW_MONTHS[hdate.month]
    year = hdate.hebrew_date_string().split()[-1]
    return f"{day} {month} {year}"


def _hebrew_year_str(hdate) -> str:
    return hdate.hebrew_date_string().split()[-1]


def _semester(hdate) -> str:
    m = hdate.month
    if m in (6, 7):
        return "אלול"
    if 2 <= m <= 5:
        return "קיץ"
    return "חורף"


# ---------------------------------------------------------------------------
# Preview + confirm
# ---------------------------------------------------------------------------

async def _show_preview(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["upload"]
    preview = _format_preview(state["form"], state["filename"])
    await msg.reply_text(
        f"📋 *סיכום השיעור:*\n\n{preview}\n\nהאם לשמור?",
        parse_mode="Markdown",
        reply_markup=confirm_upload_keyboard(),
    )


async def confirm_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("upload")
    if not state:
        await update.callback_query.answer("אין העלאה פעילה.")
        return

    form = state["form"]
    missing = [label for key, label, mandatory, _ in STEPS if mandatory and not form.get(key)]
    if missing:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "⚠️ חסרים שדות חובה:\n" + "\n".join(f"• {l}" for l in missing)
        )
        return

    await update.callback_query.answer()
    msg = update.callback_query.message

    status = await msg.reply_text("⬛⬜⬜⬜ מוריד מטלגרם...")

    filename = state["filename"]

    try:
        from .. import telethon_client
        audio_bytes = await telethon_client.download_file(
            state["chat_id"], state["message_id"]
        )
    except Exception as e:
        await status.edit_text(f"❌ שגיאה בהורדה מטלגרם:\n{e}")
        return

    await status.edit_text("⬛⬛⬜⬜ מעלה ל-R2...")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"
    today = datetime.now().date()
    fake_message_id = int(datetime.now().timestamp())
    r2_path = f"audio/{today.year}/{fake_message_id}.{ext}"

    try:
        await r2.upload_audio(audio_bytes, r2_path)
    except Exception as e:
        await status.edit_text(f"❌ שגיאה בהעלאה ל-R2:\n{e}")
        return

    await status.edit_text("⬛⬛⬛⬜ שומר בבסיס הנתונים...")

    try:
        # ------------------------------------------------------------------
        # Resolve entity IDs — create new records if name is new
        # ------------------------------------------------------------------
        teacher_id = form.get("teacher_id")
        if not teacher_id and form.get("teacher"):
            teacher_id = db.get_or_create_teacher(form["teacher"])

        series_id = form.get("series_id")
        if not series_id and form.get("series_name"):
            series_id = db.get_or_create_series(form["series_name"], teacher_id)

        # ------------------------------------------------------------------
        # Hebrew date fields (computed from today's date)
        # ------------------------------------------------------------------
        hdate = hebdates.HebrewDate.from_pydate(today)

        # ------------------------------------------------------------------
        # Build row
        # ------------------------------------------------------------------
        title = form.get("title") or form.get("series_name") or form.get("teacher") or filename
        notes = form.get("notes")
        if notes:
            title = f"{title} — {notes}"

        row = {
            "message_id": fake_message_id,
            "title": title,
            "filename": filename,
            "date": today.isoformat(),
            "hebrew_date": _hebrew_date_str(hdate),
            "hebrew_year": _hebrew_year_str(hdate),
            "semester": _semester(hdate),
            "teacher_id": teacher_id,
            "series_id": series_id,
            "audio_downloaded": True,
            "audio_r2_path": r2_path,
            "needs_human_review": False,
            "tagged_by": "manual-upload",
            "duration_seconds": state.get("duration"),
            "file_size_bytes": state.get("file_size"),
        }
        if isinstance(form.get("lesson_number"), int):
            row["lesson_number"] = form["lesson_number"]

        db.insert_new_recording(row)
    except Exception as e:
        await status.edit_text(f"❌ שגיאה בשמירה בבסיס הנתונים:\n{e}")
        return

    try:
        preview = _format_preview(form, filename)
        await update.callback_query.get_bot().send_message(
            ADMIN_CHAT_ID,
            f"📥 שיעור חדש הועלה:\n\n{preview}",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    context.user_data.pop("upload", None)
    context.user_data.pop("awaiting", None)
    await status.edit_text("⬛⬛⬛⬛ ✅ השיעור נשמר בהצלחה!")

    # Celebration GIF
    try:
        await msg.reply_animation(UPLOAD_SUCCESS_GIF, caption="השיעור עלה! תודה רבה 🙏")
    except Exception:
        pass

    # Auto-post to group/channel
    if GROUP_CHAT_ID:
        try:
            preview = _format_preview(form, filename)
            bot = update.callback_query.get_bot()
            await bot.send_audio(
                GROUP_CHAT_ID,
                audio=state["file_id"],
                caption=f"📥 *שיעור חדש בארכיון*\n\n{preview}",
                parse_mode="Markdown",
            )
        except Exception as e:
            # Non-fatal — don't block the user
            import logging
            logging.getLogger(__name__).warning("Failed to post to group: %s", e)

    await msg.reply_text("חזרה לתפריט:", reply_markup=back_to_main())


async def restart_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if form.get("title"):
        lines.append(f"📖 {form['title']}")
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
