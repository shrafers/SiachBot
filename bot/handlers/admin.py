"""Admin review queue — /review command (admin only)."""

import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes

from .. import db
from ..keyboards import review_keyboard, back_to_main
from ..utils import format_result_card

load_dotenv()

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))


def _is_admin(update: Update) -> bool:
    uid = (update.effective_user or update.message.from_user).id if update.message else (
        update.callback_query.from_user.id if update.callback_query else 0
    )
    return uid == ADMIN_CHAT_ID


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
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
    # Remove from skipped if it was there
    skipped = context.user_data.get("review_skipped", [])
    context.user_data["review_skipped"] = [x for x in skipped if x != recording_id]
    await _show_next_review(update, context)


async def review_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int) -> None:
    skipped = context.user_data.setdefault("review_skipped", [])
    if recording_id not in skipped:
        skipped.append(recording_id)
    await update.callback_query.answer("דולג ⏭")
    await _show_next_review(update, context)
