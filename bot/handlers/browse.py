"""Browse handlers — /series, /teacher, subject areas, chavurot."""

from telegram import Update
from telegram.ext import ContextTypes

from .. import db
from ..keyboards import (
    teacher_list_keyboard,
    series_list_keyboard,
    browse_subject_keyboard,
    sub_discipline_keyboard,
    chavurot_keyboard,
    back_to_main,
)
from ..utils import total_pages
from .results import send_results_page


# ---------------------------------------------------------------------------
# /teacher
# ---------------------------------------------------------------------------

async def teacher_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_teacher_list(update, context, page=0)


async def show_teacher_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    await _show_teacher_list(update, context, page)


async def _show_teacher_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    all_teachers = db.get_teacher_list()
    total = len(all_teachers)
    start = page * db.LIST_SIZE
    teachers = all_teachers[start: start + db.LIST_SIZE]

    msg = update.message or update.callback_query.message
    tp = total_pages(total, db.LIST_SIZE)
    await msg.reply_text(
        f"👤 *מרצים* ({total}) — עמוד {page+1}/{tp}",
        parse_mode="Markdown",
        reply_markup=teacher_list_keyboard(teachers, page, total),
    )


async def show_teacher_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE, teacher_id: int, page: int
) -> None:
    results = db.get_recordings_by_teacher(teacher_id, page)
    total = db.count_by_teacher(teacher_id)
    tp = total_pages(total, db.PAGE_SIZE)

    teacher_name = results[0]["teacher_name"] if results else f"מרצה {teacher_id}"
    await send_results_page(
        update, context,
        results=results,
        header=f"👤 *{teacher_name}* — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="teacher_recs",
        context_id=teacher_id,
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# /series
# ---------------------------------------------------------------------------

async def series_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_series_list(update, context, page=0)


async def show_series_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    await _show_series_list(update, context, page)


async def _show_series_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    series = db.get_series_list(page)
    total = db.count_series()
    tp = total_pages(total, db.LIST_SIZE)

    msg = update.message or update.callback_query.message
    await msg.reply_text(
        f"📖 *סדרות* ({total}) — עמוד {page+1}/{tp}",
        parse_mode="Markdown",
        reply_markup=series_list_keyboard(series, page, total),
    )


async def show_series_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE, series_id: int, page: int
) -> None:
    results = db.get_recordings_by_series(series_id, page)
    total = db.count_by_series(series_id)
    tp = total_pages(total, db.PAGE_SIZE)

    series_name = results[0]["series_name"] if results else f"סדרה {series_id}"
    await send_results_page(
        update, context,
        results=results,
        header=f"📚 *{series_name}* — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="series_recs",
        context_id=series_id,
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Subject areas
# ---------------------------------------------------------------------------

async def show_subject_areas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    areas = db.get_subject_areas()
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        "📂 *בחר תחום:*",
        parse_mode="Markdown",
        reply_markup=browse_subject_keyboard(areas),
    )


async def show_sub_disciplines(
    update: Update, context: ContextTypes.DEFAULT_TYPE, subject_area_id: int
) -> None:
    subs = db.get_sub_disciplines(subject_area_id)
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        "📂 *בחר תת-תחום:*",
        parse_mode="Markdown",
        reply_markup=sub_discipline_keyboard(subs, subject_area_id),
    )


async def show_sub_discipline_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sub_discipline_id: int, page: int
) -> None:
    results = db.get_recordings_by_sub_discipline(sub_discipline_id, page)
    total = db.count_by_sub_discipline(sub_discipline_id)
    tp = total_pages(total, db.PAGE_SIZE)

    sub_name = results[0]["sub_discipline_name"] if results else f"תת-תחום {sub_discipline_id}"
    await send_results_page(
        update, context,
        results=results,
        header=f"📂 *{sub_name}* — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="browse_sub",
        context_id=sub_discipline_id,
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Chavurot
# ---------------------------------------------------------------------------

async def show_chavurot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chavurot = db.get_chavurot()
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        "🏠 *בחר חבורה:*",
        parse_mode="Markdown",
        reply_markup=chavurot_keyboard(chavurot),
    )


async def show_chavura_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chavura_id: int, page: int
) -> None:
    results = db.get_recordings_by_chavura(chavura_id, page)
    total = db.count_by_chavura(chavura_id)
    tp = total_pages(total, db.PAGE_SIZE)

    chavura_name = results[0]["chavura_name"] if results else f"חבורה {chavura_id}"
    await send_results_page(
        update, context,
        results=results,
        header=f"🏠 *{chavura_name}* — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="browse_chav",
        context_id=chavura_id,
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Recent
# ---------------------------------------------------------------------------

async def show_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = db.get_recent_recordings(10)
    msg = update.message or update.callback_query.message
    if not results:
        await msg.reply_text("אין שיעורים עדיין.", reply_markup=back_to_main())
        return
    await send_results_page(
        update, context,
        results=results,
        header="🕐 *שיעורים אחרונים*",
        context_action="recent",
        page=0,
        total_pages=1,
    )
