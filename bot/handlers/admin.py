"""Admin & trusted-user commands: /review, /manage, /trust."""

import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes

from .. import db
from ..keyboards import (
    review_keyboard, back_to_main,
    manage_actions_keyboard, manage_series_pick_keyboard,
    manage_teacher_pick_keyboard, manage_confirm_keyboard,
)
from ..utils import format_result_card

load_dotenv()

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID


def is_trusted(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID or user_id in db.get_trusted_user_ids()


def _get_user_id(update: Update) -> int:
    if update.message:
        return update.message.from_user.id
    if update.callback_query:
        return update.callback_query.from_user.id
    return 0


# ---------------------------------------------------------------------------
# /review — admin review queue
# ---------------------------------------------------------------------------

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(_get_user_id(update)):
        await update.message.reply_text("אין לך הרשאה לפקודה זו.")
        return
    context.user_data["review_skipped"] = []
    await _show_next_review(update, context)


async def _show_next_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    skipped = context.user_data.get("review_skipped", [])
    rec = db.needs_review_next(skip_ids=skipped)

    msg = update.message or update.callback_query.message

    if not rec:
        await msg.reply_text("✅ אין שיעורים הממתינים לבדיקה!", reply_markup=back_to_main())
        return

    card = format_result_card(rec)
    await msg.reply_text(
        f"🔍 *לבדיקה:*\n\n{card}",
        parse_mode="Markdown",
        reply_markup=review_keyboard(rec["id"]),
    )


# Called from callbacks.py
async def review_approve(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    db.mark_reviewed(recording_id)
    await update.callback_query.answer("אושר ✅")
    skipped = context.user_data.get("review_skipped", [])
    context.user_data["review_skipped"] = [x for x in skipped if x != recording_id]
    await _show_next_review(update, context)


async def review_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    skipped = context.user_data.setdefault("review_skipped", [])
    if recording_id not in skipped:
        skipped.append(recording_id)
    await update.callback_query.answer("דולג ⏭")
    await _show_next_review(update, context)


# ---------------------------------------------------------------------------
# /manage — find and manage a recording by #id
# ---------------------------------------------------------------------------

async def manage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_trusted(_get_user_id(update)):
        await update.message.reply_text("אין לך הרשאה לפקודה זו.")
        return

    args = context.args
    if args and args[0].lstrip("#").isdigit():
        recording_id = int(args[0].lstrip("#"))
        await _show_manage_view(update, context, recording_id)
    else:
        context.user_data["awaiting"] = "manage_id"
        await update.message.reply_text("שלח מספר שיעור (לדוגמה: 247 או #247):")


async def handle_manage_id_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called from text router when awaiting == 'manage_id'."""
    text = update.message.text.strip().lstrip("#")
    if not text.isdigit():
        await update.message.reply_text("נא לשלוח מספר שיעור בלבד.")
        return
    context.user_data.pop("awaiting", None)
    await _show_manage_view(update, context, int(text))


async def _show_manage_view(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    msg = update.message or update.callback_query.message

    if not rec:
        await msg.reply_text(f"שיעור #{recording_id} לא נמצא.")
        return

    card = format_result_card(rec)
    await msg.reply_text(
        f"⚙️ *ניהול שיעור:*\n\n{card}",
        parse_mode="Markdown",
        reply_markup=manage_actions_keyboard(recording_id),
    )


# Called from callbacks.py
async def show_manage_view_cb(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    """Re-show manage view (e.g. after a cancelled action)."""
    await _show_manage_view(update, context, recording_id)


# ---------------------------------------------------------------------------
# Manage — pick series
# ---------------------------------------------------------------------------

async def manage_pick_series(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    if not rec:
        await update.callback_query.message.reply_text("שיעור לא נמצא.")
        return

    teacher_id = rec.get("teacher_id")
    if teacher_id:
        series = db.get_series_by_teacher(teacher_id)
    else:
        series = db.get_series_list(page=0)

    if not series:
        await update.callback_query.message.reply_text("לא נמצאו סדרות.")
        return

    await update.callback_query.message.reply_text(
        f"בחר סדרה עבור שיעור #{recording_id}:",
        reply_markup=manage_series_pick_keyboard(series, recording_id),
    )


async def manage_confirm_series(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int, series_id: int) -> None:
    series_list = db.get_series_by_teacher(0) or []  # fallback — will just use name from series table
    sb_resp = db.get_supabase().table("series").select("name").eq("id", series_id).maybe_single().execute()
    series_name = sb_resp.data["name"] if sb_resp.data else f"#{series_id}"

    rec = db.get_recording_by_display_id(recording_id)
    title = rec.get("title") or f"#{recording_id}" if rec else f"#{recording_id}"

    await update.callback_query.message.reply_text(
        f'להעביר את *{_esc(title)}* לסדרה *{_esc(series_name)}*?',
        parse_mode="Markdown",
        reply_markup=manage_confirm_keyboard("mg_ser_ok", recording_id, sid=series_id),
    )


async def manage_apply_series(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int, series_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    old_series_id = rec.get("series_id") if rec else None
    db.update_recording_series(recording_id, series_id)
    if old_series_id and old_series_id != series_id:
        db.delete_series_if_empty(old_series_id)
    await update.callback_query.answer("✅ סדרה עודכנה")
    await _show_manage_view(update, context, recording_id)


async def manage_remove_series(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    title = rec.get("title") or f"#{recording_id}" if rec else f"#{recording_id}"
    await update.callback_query.message.reply_text(
        f'להסיר סדרה מ*{_esc(title)}*?',
        parse_mode="Markdown",
        reply_markup=manage_confirm_keyboard("mg_rm_ser_ok", recording_id),
    )


async def manage_apply_remove_series(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    old_series_id = rec.get("series_id") if rec else None
    db.update_recording_series(recording_id, None)
    db.delete_series_if_empty(old_series_id)
    await update.callback_query.answer("✅ סדרה הוסרה")
    await _show_manage_view(update, context, recording_id)


# ---------------------------------------------------------------------------
# Manage — pick teacher
# ---------------------------------------------------------------------------

async def manage_pick_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    teachers = db.get_teacher_list()
    if not teachers:
        await update.callback_query.message.reply_text("לא נמצאו מרצים.")
        return
    await update.callback_query.message.reply_text(
        f"בחר מרצה עבור שיעור #{recording_id}:",
        reply_markup=manage_teacher_pick_keyboard(teachers, recording_id),
    )


async def manage_confirm_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int, teacher_id: int) -> None:
    sb_resp = db.get_supabase().table("teachers").select("name").eq("id", teacher_id).maybe_single().execute()
    teacher_name = sb_resp.data["name"] if sb_resp.data else f"#{teacher_id}"

    rec = db.get_recording_by_display_id(recording_id)
    title = rec.get("title") or f"#{recording_id}" if rec else f"#{recording_id}"

    await update.callback_query.message.reply_text(
        f'לשייך את *{_esc(title)}* ל*{_esc(teacher_name)}*?',
        parse_mode="Markdown",
        reply_markup=manage_confirm_keyboard("mg_tea_ok", recording_id, tid=teacher_id),
    )


async def manage_apply_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int, teacher_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    old_teacher_id = rec.get("teacher_id") if rec else None
    db.update_recording_teacher(recording_id, teacher_id)
    if old_teacher_id and old_teacher_id != teacher_id:
        db.delete_teacher_if_empty(old_teacher_id)
    await update.callback_query.answer("✅ מרצה עודכן")
    await _show_manage_view(update, context, recording_id)


async def manage_remove_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    title = rec.get("title") or f"#{recording_id}" if rec else f"#{recording_id}"
    await update.callback_query.message.reply_text(
        f'להסיר מרצה מ*{_esc(title)}*?',
        parse_mode="Markdown",
        reply_markup=manage_confirm_keyboard("mg_rm_tea_ok", recording_id),
    )


async def manage_apply_remove_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    old_teacher_id = rec.get("teacher_id") if rec else None
    db.update_recording_teacher(recording_id, None)
    db.delete_teacher_if_empty(old_teacher_id)
    await update.callback_query.answer("✅ מרצה הוסר")
    await _show_manage_view(update, context, recording_id)


# ---------------------------------------------------------------------------
# Manage — edit title
# ---------------------------------------------------------------------------

async def manage_edit_title_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    context.user_data["awaiting"] = "manage_title"
    context.user_data["manage_recording_id"] = recording_id
    await update.callback_query.message.reply_text(f"שלח את הכותרת החדשה לשיעור #{recording_id}:")


async def handle_manage_title_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called from text router when awaiting == 'manage_title'."""
    recording_id = context.user_data.pop("manage_recording_id", None)
    context.user_data.pop("awaiting", None)
    if not recording_id:
        return
    new_title = update.message.text.strip()
    db.update_recording_title(recording_id, new_title)
    await update.message.reply_text(f"✅ כותרת עודכנה לשיעור #{recording_id}.")
    await _show_manage_view(update, context, recording_id)


# ---------------------------------------------------------------------------
# Manage — delete (soft)
# ---------------------------------------------------------------------------

async def manage_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    title = rec.get("title") or f"#{recording_id}" if rec else f"#{recording_id}"
    teacher = rec.get("teacher_name") or "" if rec else ""
    subtitle = f" — {teacher}" if teacher else ""
    await update.callback_query.message.reply_text(
        f"⚠️ *למחוק את שיעור #{recording_id}?*\n_{_esc(title)}{_esc(subtitle)}_\n\nפעולה זו ניתנת לביטול על ידי מנהל.",
        parse_mode="Markdown",
        reply_markup=manage_confirm_keyboard("mg_del_ok", recording_id),
    )


async def manage_apply_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    rec = db.get_recording_by_display_id(recording_id)
    old_series_id = rec.get("series_id") if rec else None
    old_teacher_id = rec.get("teacher_id") if rec else None
    db.soft_delete_recording(recording_id)
    db.delete_series_if_empty(old_series_id)
    db.delete_teacher_if_empty(old_teacher_id)
    await update.callback_query.answer("🗑 שיעור נמחק")
    await update.callback_query.message.reply_text(f"✅ שיעור #{recording_id} נמחק.")


# ---------------------------------------------------------------------------
# /trust — manage trusted users (admin only)
# ---------------------------------------------------------------------------

async def trust_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(_get_user_id(update)):
        await update.message.reply_text("אין לך הרשאה לפקודה זו.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "שימוש:\n"
            "/trust list — רשימת משתמשים מורשים\n"
            "/trust add <user_id> — הוסף משתמש\n"
            "/trust remove <user_id> — הסר משתמש"
        )
        return

    subcmd = args[0].lower()

    if subcmd == "list":
        users = db.list_trusted_users()
        if not users:
            await update.message.reply_text("אין משתמשים מורשים כרגע.")
            return
        lines = [f"• `{u['telegram_user_id']}` (נוסף: {str(u['added_at'])[:10]})" for u in users]
        await update.message.reply_text("משתמשים מורשים:\n" + "\n".join(lines), parse_mode="Markdown")

    elif subcmd == "add" and len(args) >= 2 and args[1].isdigit():
        uid = int(args[1])
        db.add_trusted_user(uid, added_by=_get_user_id(update))
        await update.message.reply_text(f"✅ משתמש `{uid}` נוסף כמורשה.", parse_mode="Markdown")

    elif subcmd == "remove" and len(args) >= 2 and args[1].isdigit():
        uid = int(args[1])
        db.remove_trusted_user(uid)
        await update.message.reply_text(f"✅ משתמש `{uid}` הוסר.", parse_mode="Markdown")

    else:
        await update.message.reply_text("פקודה לא תקינה. השתמש ב: /trust list | add <id> | remove <id>")


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    for ch in r"_*`[":
        text = text.replace(ch, f"\\{ch}")
    return text
