"""Browse handlers — /series, /teacher, subject areas, chavurot."""

from telegram import Update
from telegram.ext import ContextTypes

from .. import db
from ..keyboards import (
    teacher_list_keyboard,
    teacher_series_keyboard,
    series_list_keyboard,
    chavurot_keyboard,
    hebrew_years_keyboard,
    zmanim_keyboard,
    back_to_main,
)
from ..utils import total_pages
from .results import send_results_page


# ---------------------------------------------------------------------------
# /teacher → teacher list
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


# ---------------------------------------------------------------------------
# Teacher → series list (chronological) + שיעורים בודדים
# ---------------------------------------------------------------------------

async def show_teacher_series(
    update: Update, context: ContextTypes.DEFAULT_TYPE, teacher_id: int
) -> None:
    series_list = db.get_series_by_teacher_chrono(teacher_id)
    standalone_count = db.count_standalone_by_teacher(teacher_id)
    msg = update.message or update.callback_query.message

    teacher_name = f"מרצה {teacher_id}"
    all_teachers = db.get_teacher_list()
    for t in all_teachers:
        if t["id"] == teacher_id:
            teacher_name = t["name"]
            break

    if not series_list and standalone_count == 0:
        await msg.reply_text("אין שיעורים למרצה זה.", reply_markup=back_to_main())
        return

    await msg.reply_text(
        f"👤 *{teacher_name}* — בחר סדרה:",
        parse_mode="Markdown",
        reply_markup=teacher_series_keyboard(series_list, teacher_id, standalone_count),
    )


# ---------------------------------------------------------------------------
# Teacher standalone recordings (no series)
# ---------------------------------------------------------------------------

async def show_teacher_standalone_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE, teacher_id: int, page: int
) -> None:
    results = db.get_standalone_recordings_by_teacher(teacher_id, page)
    total = db.count_standalone_by_teacher(teacher_id)
    tp = total_pages(total, db.PAGE_SIZE)

    teacher_name = results[0]["teacher_name"] if results else f"מרצה {teacher_id}"
    await send_results_page(
        update, context,
        results=results,
        header=f"👤 *{teacher_name}* — 📌 שיעורים בודדים — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="teacher_standalone",
        context_id=teacher_id,
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# All recordings for a teacher (used by "עוד כמו זה" fallback)
# ---------------------------------------------------------------------------

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
        context_action="teacher_recent",
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
# Browse by Zman (Hebrew year + semester)
# ---------------------------------------------------------------------------

async def show_zmanim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of Hebrew years."""
    years = db.get_hebrew_years()
    msg = update.message or update.callback_query.message
    if not years:
        await msg.reply_text("אין שיעורים עם שנה עברית.", reply_markup=back_to_main())
        return
    await msg.reply_text(
        "📅 *בחר שנה:*",
        parse_mode="Markdown",
        reply_markup=hebrew_years_keyboard(years),
    )


async def show_zman_year(
    update: Update, context: ContextTypes.DEFAULT_TYPE, hebrew_year: str
) -> None:
    """Show semester buttons for a given Hebrew year."""
    zmanim = db.get_zmanim_by_year(hebrew_year)
    msg = update.message or update.callback_query.message
    if not zmanim:
        await msg.reply_text("אין שיעורים בשנה זו.", reply_markup=back_to_main())
        return
    await msg.reply_text(
        f"📅 *{hebrew_year}* — בחר זמן:",
        parse_mode="Markdown",
        reply_markup=zmanim_keyboard(zmanim, hebrew_year),
    )


async def show_zman_recordings(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    hebrew_year: str, semester: str, page: int
) -> None:
    """Show recordings for a specific Hebrew year + semester."""
    results = db.get_recordings_by_year_and_semester(hebrew_year, semester, page)
    total = db.count_by_year_and_semester(hebrew_year, semester)
    tp = total_pages(total, db.PAGE_SIZE)

    await send_results_page(
        update, context,
        results=results,
        header=f"📅 *{hebrew_year} — {semester}* — {total} שיעורים, עמוד {page+1}/{tp}",
        context_action="zman_recs",
        context_extra={"y": hebrew_year, "s": semester},
        page=page,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Recent (global)
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
