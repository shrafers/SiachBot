"""Shared helper for rendering a page of recording result cards."""

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..utils import format_result_card, encode_cb
from ..keyboards import result_card_keyboard
from . import admin as admin_handlers


async def send_results_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    results: list[dict],
    header: str,
    context_action: str,
    page: int,
    total_pages: int,
    context_id: int | None = None,
    context_query: str | None = None,
    context_filter: str | None = None,
    context_extra: dict | None = None,
    filter_keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Send each result as a separate message with its own inline keyboard."""
    msg = update.message or (update.callback_query and update.callback_query.message)
    if not msg:
        return

    user_id = (update.effective_user or update.message.from_user).id if update.message else (
        update.callback_query.from_user.id if update.callback_query else 0
    )
    trusted = admin_handlers.is_trusted(user_id)

    # Send header
    await msg.reply_text(header, parse_mode="Markdown")

    for i, rec in enumerate(results):
        card_text = format_result_card(rec)

        keyboard = result_card_keyboard(
            rec=rec,
            page=page,
            total_pages=total_pages,
            context_action=context_action,
            context_id=context_id,
            context_query=context_query,
            context_filter=context_filter,
            context_extra=context_extra,
            is_trusted=trusted,
        )

        await msg.reply_text(card_text, parse_mode="Markdown", reply_markup=keyboard)

    # Send filter keyboard as a separate trailing message if provided
    if filter_keyboard:
        await msg.reply_text("סנן תוצאות:", reply_markup=filter_keyboard)
