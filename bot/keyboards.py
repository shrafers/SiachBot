"""Inline keyboard builders for all bot flows."""

import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .utils import encode_cb
from .db import PAGE_SIZE, LIST_SIZE


# ---------------------------------------------------------------------------
# Main menus
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔍 חיפוש", callback_data=encode_cb("search_prompt")),
            InlineKeyboardButton(
                "📚 לפי מרצה", callback_data=encode_cb("browse_teachers", p=0)),
        ],
        [
            InlineKeyboardButton(
                "📖 סדרות", callback_data=encode_cb("browse_series", p=0)),
            InlineKeyboardButton(
                "📅 לפי זמן", callback_data=encode_cb("browse_zmanim")),
        ],
        [
            InlineKeyboardButton(
                "🕐 אחרונים", callback_data=encode_cb("recent")),
            InlineKeyboardButton(
                "⬆️ העלאת שיעור", callback_data=encode_cb("upload_prompt")),
        ],
        [
            InlineKeyboardButton(
                "🎙 הקלטת שיעור", callback_data=encode_cb("record_prompt")),
        ],
    ])


def teacher_series_keyboard(series_list: list[dict], teacher_id: int, standalone_count: int = 0) -> InlineKeyboardMarkup:
    """Series list for a teacher, with optional שיעורים בודדים entry."""
    rows = []
    for s in series_list:
        label = s["name"]
        rows.append([InlineKeyboardButton(
            label,
            callback_data=encode_cb("series_recs", id=s["id"], p=0),
        )])
    if standalone_count > 0:
        rows.append([InlineKeyboardButton(
            f"📌 שיעורים בודדים ({standalone_count})",
            callback_data=encode_cb("teacher_standalone", tid=teacher_id, p=0),
        )])
    rows.append([InlineKeyboardButton(
        "🔙 חזרה", callback_data=encode_cb("browse_teachers", p=0))])
    return InlineKeyboardMarkup(rows)


def chavurot_keyboard(chavurot: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for c in chavurot:
        count = c.get("count", "")
        label = f"{c['name']} ({count})" if count else c["name"]
        rows.append([InlineKeyboardButton(
            label,
            callback_data=encode_cb("browse_chav", id=c["id"]),
        )])
    rows.append([InlineKeyboardButton(
        "🔙 חזרה", callback_data=encode_cb("main_menu"))])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Paginated list keyboards (teachers / series)
# ---------------------------------------------------------------------------

def teacher_list_keyboard(teachers: list[dict], page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for t in teachers:
        count = t.get("count", "")
        label = f"{t['name']} ({count})" if count else t["name"]
        rows.append([InlineKeyboardButton(
            label,
            callback_data=encode_cb("teacher_recs", id=t["id"], p=0),
        )])
    rows.append(_pagination_row("browse_teachers", page, total, LIST_SIZE))
    rows.append([InlineKeyboardButton(
        "🔙 חזרה", callback_data=encode_cb("main_menu"))])
    return InlineKeyboardMarkup(rows)


def series_list_keyboard(series: list[dict], page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for s in series:
        teacher = s.get("teacher_name") or s.get("teachers_name") or ""
        label = s["name"]
        if teacher:
            label += f" | {teacher}"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=encode_cb("series_recs", id=s["id"], p=0),
        )])
    rows.append(_pagination_row("browse_series", page, total, LIST_SIZE))
    rows.append([InlineKeyboardButton(
        "🔙 חזרה", callback_data=encode_cb("main_menu"))])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Browse by Zman (Hebrew year + semester)
# ---------------------------------------------------------------------------

def hebrew_years_keyboard(years: list[dict]) -> InlineKeyboardMarkup:
    """List of Hebrew years with recording counts."""
    rows = []
    for y in years:
        label = f"📅 {y['hebrew_year']} ({y['count']})"
        rows.append([InlineKeyboardButton(
            label, callback_data=encode_cb("zman_year", y=y["hebrew_year"]))])
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("main_menu"))])
    return InlineKeyboardMarkup(rows)


def zmanim_keyboard(zmanim: list[dict], hebrew_year: str) -> InlineKeyboardMarkup:
    """Semester buttons for a given Hebrew year."""
    rows = []
    for z in zmanim:
        label = f"{z['semester']} ({z['count']})"
        rows.append([InlineKeyboardButton(
            label, callback_data=encode_cb("zman_recs", y=hebrew_year, s=z["semester"], p=0))])
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("browse_zmanim"))])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Recording result card keyboard
# ---------------------------------------------------------------------------

def result_card_keyboard(
    rec: dict,
    page: int,
    total_pages: int,
    context_action: str,       # the browse/search action to page within
    context_id: int | None = None,   # teacher_id / series_id / etc.
    context_query: str | None = None,
    context_filter: str | None = None,
    context_extra: dict | None = None,  # arbitrary extra kwargs for prev/next callbacks
) -> InlineKeyboardMarkup:
    rows = []

    # Row 1: primary action — download
    rows.append([
        InlineKeyboardButton(
            "⬇ הורדה", callback_data=encode_cb("dl", id=rec["id"])),
    ])

    # Row 2: Prev / Next navigation
    if rec.get("series_name") and rec.get("series_id"):
        # Series navigation — show destination page number
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                f"◀ עמ' {page}",
                callback_data=encode_cb(
                    "series_recs", id=rec["series_id"], p=page - 1),
            ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                f"עמ' {page + 2} ▶",
                callback_data=encode_cb(
                    "series_recs", id=rec["series_id"], p=page + 1),
            ))
        if nav_row:
            rows.append(nav_row)
    else:
        # Generic pagination for search/browse context
        nav_row = []
        if context_action and page > 0:
            cb = _build_page_cb(context_action, page - 1,
                                context_id, context_query, context_filter, **(context_extra or {}))
            nav_row.append(InlineKeyboardButton("◀ הקודם", callback_data=cb))
        if context_action and page < total_pages - 1:
            cb = _build_page_cb(context_action, page + 1,
                                context_id, context_query, context_filter, **(context_extra or {}))
            nav_row.append(InlineKeyboardButton("הבא ▶", callback_data=cb))
        if nav_row:
            rows.append(nav_row)

    # Row 4: back to parent browse context
    back = _back_cb(context_action, context_id, context_extra)
    if back:
        rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=back)])

    return InlineKeyboardMarkup(rows)


def _build_page_cb(action, page, ctx_id=None, query=None, filter_type=None, **extra) -> str:
    kwargs = {"p": page, **extra}
    if ctx_id is not None:
        kwargs["id"] = ctx_id
    if query is not None:
        kwargs["q"] = query[:20]  # truncate to fit 64 bytes
    if filter_type and filter_type != "all":
        kwargs["f"] = filter_type
    return encode_cb(action, **kwargs)


def _back_cb(context_action: str, context_id=None, context_extra=None) -> str | None:
    """Return the callback_data for the 'back to parent browse' button."""
    if context_action == "series_recs":
        return encode_cb("browse_series", p=0)
    elif context_action in ("teacher_recs", "teacher_recent", "teacher_sub_recs"):
        return encode_cb("browse_teachers", p=0)
    elif context_action == "zman_recs":
        return encode_cb("browse_zmanim")
    elif context_action == "search_page":
        return encode_cb("search_prompt")
    elif context_action in ("recent", "browse_chav"):
        return encode_cb("main_menu")
    return encode_cb("main_menu")


# ---------------------------------------------------------------------------
# Search filter bar
# ---------------------------------------------------------------------------

def search_filter_keyboard(current: str = "all") -> InlineKeyboardMarkup:
    def btn(label, value):
        prefix = "✅ " if current == value else ""
        return InlineKeyboardButton(prefix + label, callback_data=encode_cb("search_filter", f=value))

    return InlineKeyboardMarkup([[
        btn("הכל", "all"),
        btn("סדרות בלבד", "series"),
        btn("שיעורים בודדים", "oneoff"),
    ]])


# ---------------------------------------------------------------------------
# Upload / confirm
# ---------------------------------------------------------------------------

def confirm_upload_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data=encode_cb("up_confirm")),
        InlineKeyboardButton("✏️ ערוך", callback_data=encode_cb("up_edit")),
        InlineKeyboardButton("❌ בטל", callback_data=encode_cb("up_cancel")),
    ]])


def upload_teacher_keyboard(main_teachers: list[dict], has_others: bool) -> InlineKeyboardMarkup:
    """Teachers with 10+ lessons as main buttons; optional 'אחרים' + 'מרצה חדש'."""
    rows = []
    # Two teachers per row to save space
    for i in range(0, len(main_teachers), 2):
        row = []
        for t in main_teachers[i:i+2]:
            row.append(InlineKeyboardButton(
                t["name"],
                callback_data=encode_cb("up_tea", id=t["id"]),
            ))
        rows.append(row)
    extra = []
    if has_others:
        extra.append(InlineKeyboardButton(
            "אחרים ▼", callback_data=encode_cb("up_tea_oth")))
    extra.append(InlineKeyboardButton(
        "➕ מרצה חדש", callback_data=encode_cb("up_tea_new")))
    rows.append(extra)
    rows.append([InlineKeyboardButton(
        "❌ בטל", callback_data=encode_cb("up_cancel"))])
    return InlineKeyboardMarkup(rows)


def upload_teacher_other_keyboard(other_teachers: list[dict]) -> InlineKeyboardMarkup:
    """Less common teachers (< 10 lessons)."""
    rows = []
    for i in range(0, len(other_teachers), 2):
        row = []
        for t in other_teachers[i:i+2]:
            row.append(InlineKeyboardButton(
                t["name"],
                callback_data=encode_cb("up_tea", id=t["id"]),
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(
        "➕ מרצה חדש", callback_data=encode_cb("up_tea_new"))])
    rows.append([InlineKeyboardButton(
        "🔙 חזרה", callback_data=encode_cb("up_tea_back"))])
    return InlineKeyboardMarkup(rows)


def upload_skip_keyboard() -> InlineKeyboardMarkup:
    """Single skip button for optional text steps."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("דלג ⏭", callback_data=encode_cb("up_skip")),
        InlineKeyboardButton("❌ בטל", callback_data=encode_cb("up_cancel")),
    ]])


def upload_series_keyboard(series: list[dict]) -> InlineKeyboardMarkup:
    """Series selection: existing series, standalone option, new series."""
    rows = []
    for s in series:
        label = s["name"]
        if s.get("total_lessons"):
            label += f" ({s['total_lessons']} שיעורים)"
        rows.append([InlineKeyboardButton(
            label, callback_data=encode_cb("up_ser", id=s["id"]))])
    rows.append([
        InlineKeyboardButton(
            "📌 ללא סדרה", callback_data=encode_cb("up_ser_none")),
        InlineKeyboardButton(
            "➕ סדרה חדשה", callback_data=encode_cb("up_ser_new")),
    ])
    rows.append([InlineKeyboardButton(
        "❌ בטל", callback_data=encode_cb("up_cancel"))])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Admin review
# ---------------------------------------------------------------------------

def review_keyboard(recording_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data=encode_cb(
            "rev_ok", id=recording_id)),
        InlineKeyboardButton("✏️ ערוך", callback_data=encode_cb(
            "rev_edit", id=recording_id)),
        InlineKeyboardButton("⏭ דלג", callback_data=encode_cb(
            "rev_skip", id=recording_id)),
    ]])


# ---------------------------------------------------------------------------
# Back button helpers
# ---------------------------------------------------------------------------

def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔙 תפריט ראשי", callback_data=encode_cb("main_menu"))
    ]])


# ---------------------------------------------------------------------------
# Internal: pagination nav row
# ---------------------------------------------------------------------------

def _pagination_row(action: str, page: int, total: int, page_size: int) -> list[InlineKeyboardButton]:
    total_p = max(1, math.ceil(total / page_size))
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(
            "◀ הקודם", callback_data=encode_cb(action, p=page - 1)))
    row.append(InlineKeyboardButton(
        f"{page + 1}/{total_p}", callback_data="noop"))
    if page < total_p - 1:
        row.append(InlineKeyboardButton(
            "הבא ▶", callback_data=encode_cb(action, p=page + 1)))
    return row
