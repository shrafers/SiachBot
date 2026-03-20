"""Bot entry point — run with: python -m bot"""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .handlers.start import start
from .handlers.search import search_command, handle_search_text
from .handlers.browse import series_command, teacher_command
from .handlers.upload import (
    handle_audio, handle_form_reply,
    handle_new_teacher_text, handle_new_subdiscipline_text,
)
from .handlers.admin import review_command
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
    awaiting = context.user_data.get("awaiting")

    if awaiting == "search_query":
        await handle_search_text(update, context)
    elif awaiting == "upload_form":
        await handle_form_reply(update, context)
    elif awaiting == "upload_new_teacher":
        await handle_new_teacher_text(update, context)
    elif awaiting == "upload_new_subdiscipline":
        await handle_new_subdiscipline_text(update, context)
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
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("series", series_command))
    app.add_handler(CommandHandler("teacher", teacher_command))
    app.add_handler(CommandHandler("review", review_command))

    # Audio files
    app.add_handler(MessageHandler(AUDIO_FILTER, handle_audio))

    # Free text router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text_router))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot started — polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
