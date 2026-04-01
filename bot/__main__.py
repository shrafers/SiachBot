"""Bot entry point — run with: python -m bot"""

import logging
import os
from datetime import time as dtime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .handlers.start import start, help_handler
from .handlers.search import search_command, handle_search_text
from .handlers.browse import series_command, teacher_command
from .handlers.upload import (
    handle_audio, handle_form_reply,
    handle_new_teacher_text, handle_new_series_text,
)
from .handlers.admin import (
    review_command, manage_command, trust_command,
    handle_manage_id_text, handle_manage_title_text,
    stats_command,
)
from .handlers.callbacks import handle_callback

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

AUDIO_FILTER = filters.AUDIO | filters.VOICE | filters.Document.AUDIO


async def _text_router(update: Update, context) -> None:
    """Route free-text messages based on what the bot is currently awaiting."""
    text = (update.message.text or "").strip()
    awaiting = context.user_data.get("awaiting")

    # Persistent bottom-keyboard buttons — always handled regardless of state
    if text == "🏠 תפריט ראשי":
        await start(update, context)
        return
    elif text == "❓ עזרה":
        await help_handler(update, context)
        return
    elif text == "🔍 חיפוש":
        context.user_data["awaiting"] = "search_query"
        await update.message.reply_text("הקלד את מה שאתה מחפש:")
        return
    elif text == "⬆️ העלאת שיעור":
        context.user_data["awaiting"] = "upload_audio"
        await update.message.reply_text("שלח קובץ שמע (mp3/m4a/ogg) עם כיתוב אופציונלי:")
        return

    if text == "⚙️ ניהול":
        from .handlers.admin import is_trusted
        if is_trusted(update.message.from_user.id):
            context.user_data["awaiting"] = "manage_id"
            await update.message.reply_text("שלח מספר שיעור (לדוגמה: 247 או #247):")
        return

    if awaiting == "search_query":
        await handle_search_text(update, context)
    elif awaiting == "upload_form":
        await handle_form_reply(update, context)
    elif awaiting == "upload_new_teacher":
        await handle_new_teacher_text(update, context)
    elif awaiting == "upload_new_series":
        await handle_new_series_text(update, context)
    elif awaiting == "manage_id":
        await handle_manage_id_text(update, context)
    elif awaiting == "manage_title":
        await handle_manage_title_text(update, context)
    else:
        # Unrecognised text — show main menu hint
        from .handlers.start import WELCOME
        from .keyboards import main_menu_keyboard
        await update.message.reply_text(WELCOME, reply_markup=main_menu_keyboard())


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("series", series_command))
    app.add_handler(CommandHandler("teacher", teacher_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("manage", manage_command))
    app.add_handler(CommandHandler("trust", trust_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Audio files
    app.add_handler(MessageHandler(AUDIO_FILTER, handle_audio))

    # Free text router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text_router))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Monthly cost report — runs on the 1st of each month at 08:00 UTC
    async def _send_cost_report(context) -> None:
        from cost_report import run_cost_report
        try:
            run_cost_report()
        except Exception as exc:
            logger.error("Cost report failed: %s", exc)

    app.job_queue.run_monthly(
        _send_cost_report,
        when=dtime(8, 0),
        day=1,
    )

    logger.info("Bot started — polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
