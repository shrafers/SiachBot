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
            InlineKeyboardButton("🔍 חיפוש", callback_data=encode_cb("search_prompt")),
            InlineKeyboardButton("📚 לפי מרצה", callback_data=encode_cb("browse_teachers", p=0)),
        ],
        [
            InlineKeyboardButton("📖 סדרות", callback_data=encode_cb("browse_series", p=0)),
            InlineKeyboardButton("🕐 אחרונים", callback_data=encode_cb("recent")),
        ],
        [
            InlineKeyboardButton("⬆️ העלאת שיעור", callback_data=encode_cb("upload_prompt")),
        ],
    ])


def browse_subject_keyboard(areas: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for area in areas:
        rows.append([InlineKeyboardButton(
            f"{area['name']} ({area.get('count', '')})",
            callback_data=encode_cb("browse_subj", id=area["id"]),
        )])
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("main_menu"))])
    return InlineKeyboardMarkup(rows)


def sub_discipline_keyboard(subs: list[dict], subject_area_id: int) -> InlineKeyboardMarkup:
    rows = []
    for sub in subs:
        count = sub.get("count", "")
        label = f"{sub['name']} ({count})" if count else sub["name"]
        rows.append([InlineKeyboardButton(
            label,
            callback_data=encode_cb("browse_sub", id=sub["id"]),
        )])
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("browse_subj_back", id=subject_area_id))])
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
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("main_menu"))])
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
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("main_menu"))])
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
    rows.append([InlineKeyboardButton("🔙 חזרה", callback_data=encode_cb("main_menu"))])
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
) -> InlineKeyboardMarkup:
    rows = []

    # Download button
    rows.append([
        InlineKeyboardButton("⬇ הורדה", callback_data=encode_cb("dl", id=rec["id"])),
        InlineKeyboardButton("עוד כמו זה", callback_data=encode_cb("like", id=rec["id"])),
    ])

    # Prev / Next within series
    if rec.get("series_name") and rec.get("series_id"):
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                "◀ הקודם",
                callback_data=encode_cb("series_recs", id=rec["series_id"], p=page - 1),
            ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                "הבא ▶",
                callback_data=encode_cb("series_recs", id=rec["series_id"], p=page + 1),
            ))
        if nav_row:
            rows.append(nav_row)
    else:
        # Generic pagination for search/browse context
        nav_row = []
        if context_action and page > 0:
            cb = _build_page_cb(context_action, page - 1, context_id, context_query, context_filter)
            nav_row.append(InlineKeyboardButton("◀ הקודם", callback_data=cb))
        if context_action and page < total_pages - 1:
            cb = _build_page_cb(context_action, page + 1, context_id, context_query, context_filter)
            nav_row.append(InlineKeyboardButton("הבא ▶", callback_data=cb))
        if nav_row:
            rows.append(nav_row)

    return InlineKeyboardMarkup(rows)


def _build_page_cb(action, page, ctx_id=None, query=None, filter_type=None) -> str:
    kwargs = {"p": page}
    if ctx_id is not None:
        kwargs["id"] = ctx_id
    if query is not None:
        kwargs["q"] = query[:20]  # truncate to fit 64 bytes
    if filter_type and filter_type != "all":
        kwargs["f"] = filter_type
    return encode_cb(action, **kwargs)


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


# ---------------------------------------------------------------------------
# Admin review
# ---------------------------------------------------------------------------

def review_keyboard(recording_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data=encode_cb("rev_ok", id=recording_id)),
        InlineKeyboardButton("✏️ ערוך", callback_data=encode_cb("rev_edit", id=recording_id)),
        InlineKeyboardButton("⏭ דלג", callback_data=encode_cb("rev_skip", id=recording_id)),
    ]])


# ---------------------------------------------------------------------------
# Back button helpers
# ---------------------------------------------------------------------------

def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 תפריט ראשי", callback_data=encode_cb("main_menu"))
    ]])


# ---------------------------------------------------------------------------
# Internal: pagination nav row
# ---------------------------------------------------------------------------

def _pagination_row(action: str, page: int, total: int, page_size: int) -> list[InlineKeyboardButton]:
    total_p = max(1, math.ceil(total / page_size))
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀ הקודם", callback_data=encode_cb(action, p=page - 1)))
    row.append(InlineKeyboardButton(f"{page + 1}/{total_p}", callback_data="noop"))
    if page < total_p - 1:
        row.append(InlineKeyboardButton("הבא ▶", callback_data=encode_cb(action, p=page + 1)))
    return row
