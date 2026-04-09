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
        is_admin = admin_handlers.is_admin(query.from_user.id)
        await query.message.reply_text("תפריט ראשי:", reply_markup=main_menu_keyboard(is_admin=is_admin))

    elif action == "admin_stats":
        if not admin_handlers.is_admin(query.from_user.id):
            await query.message.reply_text("אין לך הרשאה.")
            return
        await admin_handlers.stats_command(update, context)

    elif action == "search_prompt":
        context.user_data["awaiting"] = "search_query"
        await query.message.reply_text("הקלד את מונח החיפוש:")

    elif action == "upload_prompt":
        context.user_data["awaiting"] = "upload_audio"
        await query.message.reply_text("שלח קובץ שמע (mp3/m4a/ogg) עם כיתוב אופציונלי:")

    elif action == "record_prompt":
        await query.message.reply_text(
            "🎙 *להקלטת שיעור:*\n\n"
            "החזק את אייקון המיקרופון ⬇️ כדי להקליט, ושחרר כשתסיים.\n"
            "השיעור יישלח ישירות לבוט ותוכל להוסיף פרטים.",
            parse_mode="Markdown",
        )

    # ------------------------------------------------------------------
    # Browse — teachers
    # ------------------------------------------------------------------
    elif action == "browse_teachers":
        await browse.show_teacher_list(update, context, page=data.get("p", 0))

    elif action == "teacher_recs":
        # Tap on a teacher name → show their series list
        await browse.show_teacher_series(update, context, teacher_id=data["id"])

    elif action == "teacher_recent":
        # All recordings by teacher (used by "עוד כמו זה" fallback)
        await browse.show_teacher_recordings(update, context, teacher_id=data["id"], page=data.get("p", 0))

    elif action == "teacher_standalone":
        # Standalone (no-series) recordings for a teacher
        await browse.show_teacher_standalone_recordings(update, context, teacher_id=data["tid"], page=data.get("p", 0))

    # ------------------------------------------------------------------
    # Browse — series
    # ------------------------------------------------------------------
    elif action == "browse_series":
        await browse.show_series_list(update, context, page=data.get("p", 0))

    elif action == "series_recs":
        await browse.show_series_recordings(update, context, series_id=data["id"], page=data.get("p", 0))

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
    # Browse — by zman (Hebrew year + semester)
    # ------------------------------------------------------------------
    elif action == "browse_zmanim":
        await browse.show_zmanim(update, context)

    elif action == "zman_year":
        await browse.show_zman_year(update, context, hebrew_year=data["y"])

    elif action == "zman_recs":
        await browse.show_zman_recordings(
            update, context,
            hebrew_year=data["y"],
            semester=data["s"],
            page=data.get("p", 0),
        )

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
                    "teacher_id": rec.get("teacher_id"),
                    "series_name": rec.get("series_name"),
                    "series_id": rec.get("series_id"),
                    "lesson_number": rec.get("lesson_number"),
                    "notes": None,
                },
                "step": 0,
                "review_recording_id": data["id"],
            }
            context.user_data["awaiting"] = "upload_form"
            await upload_handlers.restart_form(update, context)

    # ------------------------------------------------------------------
    # Manage flow (trusted users)
    # ------------------------------------------------------------------
    elif action == "manage":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.show_manage_view_cb(update, context, recording_id=data["id"])

    elif action == "mg_series":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_pick_series(update, context, recording_id=data["id"])

    elif action == "mg_ser_pick":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_confirm_series(update, context, recording_id=data["id"], series_id=data["sid"])

    elif action == "mg_ser_ok":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_apply_series(update, context, recording_id=data["id"], series_id=data["sid"])

    elif action == "mg_rm_series":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_remove_series(update, context, recording_id=data["id"])

    elif action == "mg_rm_ser_ok":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_apply_remove_series(update, context, recording_id=data["id"])

    elif action == "mg_teacher":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_pick_teacher(update, context, recording_id=data["id"])

    elif action == "mg_tea_pick":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_confirm_teacher(update, context, recording_id=data["id"], teacher_id=data["tid"])

    elif action == "mg_tea_ok":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_apply_teacher(update, context, recording_id=data["id"], teacher_id=data["tid"])

    elif action == "mg_rm_teacher":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_remove_teacher(update, context, recording_id=data["id"])

    elif action == "mg_rm_tea_ok":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_apply_remove_teacher(update, context, recording_id=data["id"])

    elif action == "mg_title":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_edit_title_prompt(update, context, recording_id=data["id"])

    elif action == "mg_delete":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_delete_confirm(update, context, recording_id=data["id"])

    elif action == "mg_del_ok":
        if admin_handlers.is_trusted(query.from_user.id):
            await admin_handlers.manage_apply_delete(update, context, recording_id=data["id"])

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

    try:
        db.log_event(update.callback_query.from_user.id, "download", {"recording_id": recording_id})
    except Exception:
        pass

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
            await context.bot.send_chat_action(
                chat_id=update.callback_query.message.chat_id,
                action="upload_document",
            )
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

    results = total = header = ctx_action = ctx_id = None

    # 1. Same series
    if rec.get("series_id"):
        results = db.get_recordings_by_series(rec["series_id"], page=0)
        total = db.count_by_series(rec["series_id"])
        header = f"📚 עוד מהסדרה: *{rec.get('series_name', '')}*"
        ctx_action = "series_recs"
        ctx_id = rec["series_id"]

    # 2. Same teacher
    elif rec.get("teacher_id"):
        results = db.get_recordings_by_teacher(rec["teacher_id"], page=0)
        total = db.count_by_teacher(rec["teacher_id"])
        teacher = rec.get("teacher_name") or ""
        header = f"👤 עוד מ: *{teacher}*"
        ctx_action = "teacher_recent"
        ctx_id = rec["teacher_id"]

    # 3. Same studied figure (first one found)
    else:
        figures = db.get_studied_figure_ids(recording_id)
        if figures:
            fig = figures[0]
            results = db.get_recordings_by_studied_figure(fig["id"], page=0)
            total = db.count_by_studied_figure(fig["id"])
            header = f"📖 עוד על: *{fig['name']}*"
            ctx_action = "browse_sub"
            ctx_id = None

    if not results:
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
