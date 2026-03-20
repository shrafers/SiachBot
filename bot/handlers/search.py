"""Search handler — /search command and search flow."""

from telegram import Update
from telegram.ext import ContextTypes

from .. import db
from ..keyboards import search_filter_keyboard, back_to_main
from ..utils import format_result_card, total_pages, encode_cb
from .results import send_results_page

ASK_QUERY = "הקלד את מונח החיפוש (שם מרצה, נושא, סדרה...):"


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search [query] or /search with no args."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        context.user_data["awaiting"] = "search_query"
        await update.message.reply_text(ASK_QUERY)
        return
    await _do_search(update, context, query, page=0, filter_type="all")


async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive free-text query when bot is awaiting one."""
    query = update.message.text.strip()
    context.user_data.pop("awaiting", None)
    await _do_search(update, context, query, page=0, filter_type="all")


async def _do_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    page: int,
    filter_type: str,
) -> None:
    results = db.search_recordings(query, page=page, filter_type=filter_type)
    total = db.count_search(query, filter_type=filter_type)
    tp = total_pages(total, db.PAGE_SIZE)

    # Save state for pagination callbacks
    context.user_data["search"] = {
        "query": query,
        "page": page,
        "filter": filter_type,
        "total": total,
    }

    if not results:
        msg = update.message or update.callback_query.message
        await msg.reply_text(
            f"לא נמצאו תוצאות עבור: *{query}*",
            parse_mode="Markdown",
            reply_markup=back_to_main(),
        )
        return

    header = f"🔍 תוצאות עבור: *{query}* ({total} שיעורים, עמוד {page+1}/{tp})"
    await send_results_page(
        update, context,
        results=results,
        header=header,
        context_action="search_page",
        context_query=query,
        context_filter=filter_type,
        page=page,
        total_pages=tp,
        filter_keyboard=search_filter_keyboard(filter_type),
    )
