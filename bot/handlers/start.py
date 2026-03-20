"""Handler for /start command and main menu."""

from telegram import Update
from telegram.ext import ContextTypes

from ..keyboards import main_menu_keyboard

WELCOME = (
    "ברוך הבא לארכיון שיעורי הישיבה! 🎓\n"
    "בחר פעולה מהתפריט:"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, reply_markup=main_menu_keyboard())
