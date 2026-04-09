"""Handler for /start command, main menu, and /help."""

import os

from telegram import Update
from telegram.ext import ContextTypes

from ..keyboards import main_menu_keyboard, quick_access_keyboard
from . import admin as admin_handlers
from .. import db

WELCOME = (
    "ברוך הבא לארכיון שיעורי הישיבה! 🎓\n"
    "בחר פעולה מהתפריט:"
)

HELP_TEXT = (
    "🎓 *ארכיון שיעורי הישיבה*\n\n"
    "הבוט מאפשר לחפש ולהאזין לשיעורים מהארכיון של הישיבה\\.\n\n"
    "🔍 *חיפוש* — חפש לפי שם שיעור, מרצה, סדרה או נושא\n"
    "📚 *לפי מרצה* — עיין בשיעורים לפי מרצה\n"
    "📖 *סדרות* — עיין בשיעורים לפי סדרה\n"
    "🕐 *אחרונים* — השיעורים שנוספו לאחרונה\n"
    "⬆️ *העלאת שיעור* — הוסף שיעור חדש לארכיון\n\n"
    "\\-\\-\\-\n"
    "💬 *יש שאלה? בעיה? הצעה?*\n"
    "מוזמנים לפנות למנהל הבוט בכל עניין \\— נשמח לשמוע\\!\n"
    "{admin_line}\n\n"
    "{channel_line}"
)


def _build_help_text() -> str:
    admin_username = os.environ.get("ADMIN_USERNAME", "")
    channel_link = os.environ.get("CHANNEL_LINK", "")

    if admin_username:
        admin_line = f"👤 [פנה למנהל](https://t.me/{admin_username})"
    else:
        admin_line = "👤 פנה למנהל הבוט לכל שאלה או הצעה"

    if channel_link:
        channel_line = f"📢 [הצטרף לערוץ]({channel_link})"
    else:
        channel_line = ""

    return HELP_TEXT.format(admin_line=admin_line, channel_line=channel_line).strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    user_id = user.id
    try:
        db.upsert_user(user_id, user.username)
        db.log_event(user_id, "start")
    except Exception:
        pass
    trusted = admin_handlers.is_trusted(user_id)
    admin = admin_handlers.is_admin(user_id)
    # Send welcome with persistent keyboard to install/replace the bottom bar
    await update.message.reply_text(WELCOME, reply_markup=quick_access_keyboard(trusted=trusted))
    # Then show the inline main menu
    await update.message.reply_text("בחר פעולה:", reply_markup=main_menu_keyboard(is_admin=admin))


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        _build_help_text(),
        parse_mode="MarkdownV2",
        disable_web_page_preview=True,
    )
