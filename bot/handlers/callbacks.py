"""Central CallbackQueryHandler — decodes callback data and routes to handlers."""

import io
import os

from telegram import Update
from telegram.ext import ContextTypes

from .. import db, r2
from ..keyboards import main_menu_keyboard, search_filter_keyboard, back_to_main
from ..utils import decode_cb, format_result_card
from . import browse, upload as upload_handlers, admin as admin_handlers
from .search import _do_search


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        data = decode_cb(query.data)
    except Exception:
        return

    action = data.get("a")

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------
    if action == "main_menu":
        await query.message.reply_text("תפריט ראשי:", reply_markup=main_menu_keyboard())

    elif action == "search_prompt":
        context.user_data["awaiting"] = "search_query"
        await query.message.reply_text("הקלד את מונח החיפוש:")

    elif action == "upload_prompt":
        context.user_data["awaiting"] = "upload_audio"
        await query.message.reply_text("שלח קובץ שמע (mp3/m4a/ogg) עם כיתוב אופציונלי:")

    # ------------------------------------------------------------------
    # Browse — teachers
    # ------------------------------------------------------------------
    elif action == "browse_teachers":
        await browse.show_teacher_list(update, context, page=data.get("p", 0))

    elif action == "teacher_recs":
        # Tap on a teacher name → show subject areas for that teacher
        await browse.show_teacher_subjects(update, context, teacher_id=data["id"])

    elif action == "teacher_recent":
        # "Recent" button on teacher subject page → all recent by teacher
        await browse.show_teacher_recordings(update, context, teacher_id=data["id"], page=data.get("p", 0))

    elif action == "teacher_subj":
        # Tap on a subject area within a teacher → sub-disciplines
        await browse.show_teacher_sub_disciplines(update, context, teacher_id=data["tid"], subject_area_id=data["sid"])

    elif action == "teacher_subj_back":
        # Back from sub-disciplines → teacher subject areas
        await browse.show_teacher_subjects(update, context, teacher_id=data["id"])

    elif action == "teacher_subj_recent":
        # "Recent" on teacher+subject sub-discipline page
        await browse.show_teacher_subject_recent(update, context, teacher_id=data["tid"], subject_area_id=data["sid"])

    # ------------------------------------------------------------------
    # Browse — series
    # ------------------------------------------------------------------
    elif action == "browse_series":
        await browse.show_series_list(update, context, page=data.get("p", 0))

    elif action == "series_recs":
        await browse.show_series_recordings(update, context, series_id=data["id"], page=data.get("p", 0))

    # ------------------------------------------------------------------
    # Browse — subject areas / sub-disciplines
    # ------------------------------------------------------------------
    elif action == "browse_subj":
        await browse.show_sub_disciplines(update, context, subject_area_id=data["id"])

    elif action == "browse_subj_back":
        await browse.show_subject_areas(update, context)

    elif action == "subj_recent":
        await browse.show_subject_area_recent(update, context, subject_area_id=data["id"])

    elif action == "teacher_sub_recs":
        await browse.show_teacher_sub_discipline_recordings(
            update, context, teacher_id=data["tid"], sub_discipline_id=data["id"], page=data.get("p", 0)
        )

    elif action == "browse_sub":
        await browse.show_sub_discipline_recordings(update, context, sub_discipline_id=data["id"], page=data.get("p", 0))

    # ------------------------------------------------------------------
    # Browse — chavurot
    # ------------------------------------------------------------------
    elif action == "browse_chav":
        chav_id = data.get("id")
        if chav_id:
            await browse.show_chavura_recordings(update, context, chavura_id=chav_id, page=data.get("p", 0))
        else:
            await browse.show_chavurot(update, context)

    # ------------------------------------------------------------------
    # Recent
    # ------------------------------------------------------------------
    elif action == "recent":
        await browse.show_recent(update, context)

    # ------------------------------------------------------------------
    # Search pagination & filter
    # ------------------------------------------------------------------
    elif action == "search_page":
        state = context.user_data.get("search", {})
        q = data.get("q") or state.get("query", "")
        f = data.get("f") or state.get("filter", "all")
        p = data.get("p", 0)
        await _do_search(update, context, query=q, page=p, filter_type=f)

    elif action == "search_filter":
        state = context.user_data.get("search", {})
        q = state.get("query", "")
        f = data.get("f", "all")
        if q:
            await _do_search(update, context, query=q, page=0, filter_type=f)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    elif action == "dl":
        await _handle_download(update, context, recording_id=data["id"])

    # ------------------------------------------------------------------
    # "More like this"
    # ------------------------------------------------------------------
    elif action == "like":
        await _handle_like(update, context, recording_id=data["id"])

    # ------------------------------------------------------------------
    # Browse — subject areas (main menu entry point)
    # ------------------------------------------------------------------
    elif action == "browse_subjects":
        await browse.show_subject_areas(update, context)

    # ------------------------------------------------------------------
    # Upload flow — confirm / edit / cancel
    # ------------------------------------------------------------------
    elif action == "up_confirm":
        await upload_handlers.confirm_upload(update, context)

    elif action == "up_edit":
        await upload_handlers.restart_form(update, context)

    elif action == "up_cancel":
        await upload_handlers.cancel_upload(update, context)

    # ------------------------------------------------------------------
    # Upload flow — teacher selection
    # ------------------------------------------------------------------
    elif action == "up_tea":
        await upload_handlers.handle_teacher_selected(update, context, teacher_id=data["id"])

    elif action == "up_tea_oth":
        await upload_handlers.handle_teacher_other(update, context)

    elif action == "up_tea_back":
        await upload_handlers.handle_teacher_back(update, context)

    elif action == "up_tea_new":
        await upload_handlers.handle_teacher_new(update, context)

    # ------------------------------------------------------------------
    # Upload flow — subject area + sub-discipline selection
    # ------------------------------------------------------------------
    elif action == "up_subj":
        await upload_handlers.handle_subject_selected(update, context, subject_area_id=data["id"])

    elif action == "up_subj_back":
        await upload_handlers.handle_subject_back(update, context)

    elif action == "up_sub":
        await upload_handlers.handle_subdiscipline_selected(update, context, sub_id=data["id"])

    elif action == "up_sub_new":
        await upload_handlers.handle_subdiscipline_new(update, context)

    # ------------------------------------------------------------------
    # Upload flow — series selection
    # ------------------------------------------------------------------
    elif action == "up_ser":
        await upload_handlers.handle_series_selected(update, context, series_id=data["id"])

    elif action == "up_ser_none":
        await upload_handlers.handle_series_standalone(update, context)

    elif action == "up_ser_new":
        await upload_handlers.handle_series_new(update, context)

    # ------------------------------------------------------------------
    # Upload flow — skip optional step
    # ------------------------------------------------------------------
    elif action == "up_skip":
        await upload_handlers.handle_skip(update, context)

    # ------------------------------------------------------------------
    # Admin review
    # ------------------------------------------------------------------
    elif action == "rev_ok":
        await admin_handlers.review_approve(update, context, recording_id=data["id"])

    elif action == "rev_skip":
        await admin_handlers.review_skip(update, context, recording_id=data["id"])

    elif action == "rev_edit":
        # Load the recording into upload state and restart the form
        rec = db.get_recording(data["id"])
        if rec:
            context.user_data["upload"] = {
                "file_id": None,
                "filename": rec.get("filename", ""),
                "caption": "",
                "file_size": rec.get("file_size_bytes"),
                "duration": rec.get("duration_seconds"),
                "form": {
                    "teacher": rec.get("teacher_name"),
                    "subject_area": rec.get("sub_discipline_name"),
                    "sub_discipline": rec.get("sub_discipline_name"),
                    "series_name": rec.get("series_name"),
                    "lesson_number": rec.get("lesson_number"),
                    "notes": None,
                },
                "step": 0,
                "review_recording_id": data["id"],
            }
            context.user_data["awaiting"] = "upload_form"
            await upload_handlers.restart_form(update, context)

    elif action == "noop":
        pass  # pagination counter button — do nothing


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

async def _handle_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int
) -> None:
    rec = db.get_recording(recording_id)
    if not rec:
        await update.callback_query.message.reply_text("שיעור לא נמצא.")
        return

    if rec.get("audio_r2_path"):
        file_size = rec.get("file_size_bytes") or 0
        ext = os.path.splitext(rec.get("filename") or ".m4a")[1] or ".m4a"
        title_part = rec.get("title") or ""
        teacher_part = rec.get("teacher_name") or ""
        if title_part and teacher_part:
            display_name = f"{title_part} - {teacher_part}{ext}"
        elif title_part:
            display_name = f"{title_part}{ext}"
        else:
            display_name = rec.get("filename") or f"shiur_{recording_id}{ext}"
        filename = display_name
        caption = rec.get("title") or display_name

        # Telegram bot API limit is 50MB; use presigned URL for large files
        if file_size > 20 * 1024 * 1024:
            try:
                url = await r2.get_presigned_url(rec["audio_r2_path"], expires_in=3600)
                await update.callback_query.message.reply_text(
                    f"📥 הקובץ גדול מדי לשליחה ישירה.\nלחץ להורדה: [הורד שיעור]({url})",
                    parse_mode="Markdown",
                )
            except Exception as e:
                await update.callback_query.message.reply_text(f"שגיאה בהורדה: {e}")
        else:
            await update.callback_query.message.reply_text("מוריד קובץ... ⏳")
            try:
                audio_bytes = await r2.get_audio_bytes(rec["audio_r2_path"])
                await update.callback_query.message.reply_document(
                    document=io.BytesIO(audio_bytes),
                    filename=filename,
                    caption=caption,
                )
            except Exception as e:
                if "Request Entity Too Large" in str(e):
                    try:
                        url = await r2.get_presigned_url(rec["audio_r2_path"], expires_in=3600)
                        await update.callback_query.message.reply_text(
                            f"הקובץ גדול מדי לשליחה ישירה.\n[לחץ להורדה]({url})",
                            parse_mode="Markdown",
                        )
                    except Exception as e2:
                        await update.callback_query.message.reply_text(f"שגיאה בהורדה: {e2}")
                else:
                    await update.callback_query.message.reply_text(f"שגיאה בהורדה: {e}")
    else:
        link = rec.get("telegram_link") or "לא זמין"
        await update.callback_query.message.reply_text(
            f"הקובץ עדיין לא הורד.\nלינק טלגרם: {link}",
            reply_markup=back_to_main(),
        )


# ---------------------------------------------------------------------------
# "More like this" logic
# ---------------------------------------------------------------------------

async def _handle_like(
    update: Update, context: ContextTypes.DEFAULT_TYPE, recording_id: int
) -> None:
    from .results import send_results_page
    from ..utils import total_pages as _total_pages

    rec = db.get_recording(recording_id)
    if not rec:
        return

    # Priority: same series > same teacher + subject > default by teacher
    if rec.get("series_id"):
        results = db.get_recordings_by_series(rec["series_id"], page=0)
        total = db.count_by_series(rec["series_id"])
        header = f"📚 עוד מהסדרה: *{rec.get('series_name', '')}*"
        ctx_action = "series_recs"
        ctx_id = rec["series_id"]
    elif rec.get("teacher_id"):
        results = db.get_recordings_by_teacher(rec["teacher_id"], page=0)
        total = db.count_by_teacher(rec["teacher_id"])
        teacher = rec.get("teacher_name") or ""
        header = f"👤 עוד מ: *{teacher}*"
        ctx_action = "teacher_recs"
        ctx_id = rec["teacher_id"]
    else:
        await update.callback_query.message.reply_text("לא נמצאו שיעורים דומים.")
        return

    tp = _total_pages(total, db.PAGE_SIZE)
    await send_results_page(
        update, context,
        results=results,
        header=header,
        context_action=ctx_action,
        context_id=ctx_id,
        page=0,
        total_pages=tp,
    )
