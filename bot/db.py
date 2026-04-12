"""Supabase query layer — all DB interactions live here."""

import os
import time
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

PAGE_SIZE = 5   # results per page for recordings
LIST_SIZE = 10  # items per page for browse lists

# ---------------------------------------------------------------------------
# Trusted users cache (refreshed every 60 seconds)
# ---------------------------------------------------------------------------

_trusted_cache: set[int] = set()
_trusted_cache_ts: float = 0.0
_TRUSTED_CACHE_TTL = 60.0


def get_trusted_user_ids() -> set[int]:
    global _trusted_cache, _trusted_cache_ts
    if time.monotonic() - _trusted_cache_ts > _TRUSTED_CACHE_TTL:
        sb = get_supabase()
        resp = sb.table("trusted_users").select("telegram_user_id").execute()
        _trusted_cache = {r["telegram_user_id"] for r in (resp.data or [])}
        _trusted_cache_ts = time.monotonic()
    return _trusted_cache


def add_trusted_user(user_id: int, added_by: int) -> None:
    sb = get_supabase()
    sb.table("trusted_users").upsert({
        "telegram_user_id": user_id,
        "added_by": added_by,
    }).execute()
    global _trusted_cache_ts
    _trusted_cache_ts = 0.0  # invalidate cache


def remove_trusted_user(user_id: int) -> None:
    sb = get_supabase()
    sb.table("trusted_users").delete().eq("telegram_user_id", user_id).execute()
    global _trusted_cache_ts
    _trusted_cache_ts = 0.0  # invalidate cache


def list_trusted_users() -> list[dict]:
    sb = get_supabase()
    resp = sb.table("trusted_users").select("telegram_user_id, added_by, added_at").order("added_at").execute()
    return resp.data or []


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _build_search_filter(q, query: str):
    """Apply word-split ILIKE conditions on search_text to a Supabase query object."""
    tokens = [t for t in query.strip().split() if t]
    for token in tokens:
        q = q.ilike("search_text", f"%{token}%")
    return q


def search_recordings(query: str, page: int = 0, filter_type: str = "all") -> list[dict]:
    """Free-text search across title, teacher, series, and tags."""
    query = query.strip()
    if not query:
        return []
    sb = get_supabase()
    offset = page * PAGE_SIZE
    q = (
        sb.table("recordings")
        .select(
            "id, message_id, title, date, hebrew_date, is_oneoff, "
            "audio_downloaded, audio_r2_path, telegram_link, lesson_number, duration_seconds, "
            "teachers(name), series(name), chavurot(name)"
        )
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(offset, offset + PAGE_SIZE - 1)
    )
    q = _build_search_filter(q, query)
    if filter_type == "series":
        q = q.not_.is_("series_id", "null")
    elif filter_type == "oneoff":
        q = q.eq("is_oneoff", True)
    resp = q.execute()
    return _flatten_joins(resp.data or [])


def count_search(query: str, filter_type: str = "all") -> int:
    """Return total hit count for pagination."""
    query = query.strip()
    if not query:
        return 0
    sb = get_supabase()
    q = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .is_("deleted_at", "null")
    )
    q = _build_search_filter(q, query)
    if filter_type == "series":
        q = q.not_.is_("series_id", "null")
    elif filter_type == "oneoff":
        q = q.eq("is_oneoff", True)
    resp = q.execute()
    return resp.count or 0


# ---------------------------------------------------------------------------
# Browse lists
# ---------------------------------------------------------------------------

def get_teacher_list() -> list[dict]:
    """All teachers with their recording count, sorted desc."""
    sb = get_supabase()
    resp = sb.rpc("teachers_with_count").execute()
    return resp.data or []


def get_series_list(page: int = 0) -> list[dict]:
    """All series ordered by most recent lesson date (chronological)."""
    sb = get_supabase()
    resp = sb.rpc("series_chronological", {
        "p_offset": page * LIST_SIZE,
        "p_limit": LIST_SIZE,
    }).execute()
    return resp.data or []


def count_series() -> int:
    sb = get_supabase()
    resp = sb.table("series").select("id", count="exact", head=True).execute()
    return resp.count or 0


def get_chavurot() -> list[dict]:
    sb = get_supabase()
    resp = sb.rpc("chavurot_with_count").execute()
    return resp.data or []


def get_series_by_teacher(teacher_id: int) -> list[dict]:
    """All series taught by a specific teacher, sorted by name."""
    sb = get_supabase()
    resp = (
        sb.table("series")
        .select("id, name, total_lessons")
        .eq("teacher_id", teacher_id)
        .order("name")
        .execute()
    )
    return resp.data or []


def get_series_by_teacher_chrono(teacher_id: int) -> list[dict]:
    """All series for a teacher ordered by most recent lesson date DESC."""
    sb = get_supabase()
    resp = sb.rpc("series_by_teacher_chrono", {"p_teacher_id": teacher_id}).execute()
    return resp.data or []


def get_standalone_recordings_by_teacher(teacher_id: int, page: int = 0) -> list[dict]:
    """Recordings by a teacher with no series (series_id IS NULL)."""
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("teacher_id", teacher_id)
        .is_("series_id", "null")
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_standalone_by_teacher(teacher_id: int) -> int:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .eq("teacher_id", teacher_id)
        .is_("series_id", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    return resp.count or 0


def get_recent_by_teacher(teacher_id: int, limit: int = 10) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("teacher_id", teacher_id)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return _flatten_joins(resp.data or [])


# ---------------------------------------------------------------------------
# Recording lists by facet
# ---------------------------------------------------------------------------

def _recording_select():
    return (
        "id, message_id, title, date, hebrew_date, is_oneoff, "
        "teacher_id, series_id, "
        "audio_downloaded, audio_r2_path, telegram_link, lesson_number, duration_seconds, "
        "teachers(name), series(name), chavurot(name)"
    )


def get_recordings_by_teacher(teacher_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("teacher_id", teacher_id)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_teacher(teacher_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("teacher_id", teacher_id).is_("deleted_at", "null").execute()
    return resp.count or 0


def get_recordings_by_series(series_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("series_id", series_id)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_series(series_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("series_id", series_id).is_("deleted_at", "null").execute()
    return resp.count or 0


def get_recordings_by_chavura(chavura_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("chavura_id", chavura_id)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_chavura(chavura_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("chavura_id", chavura_id).is_("deleted_at", "null").execute()
    return resp.count or 0


def get_hebrew_years() -> list[dict]:
    """All Hebrew years with recording count, sorted by most recent date first."""
    sb = get_supabase()
    resp = sb.rpc("hebrew_years_with_count").execute()
    return resp.data or []


def get_zmanim_by_year(hebrew_year: str) -> list[dict]:
    """Semesters with recording count for a given Hebrew year."""
    sb = get_supabase()
    resp = sb.rpc("zmanim_by_year_with_count", {"p_year": hebrew_year}).execute()
    return resp.data or []


def get_recordings_by_year_and_semester(hebrew_year: str, semester: str, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("hebrew_year", hebrew_year)
        .eq("semester", semester)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_year_and_semester(hebrew_year: str, semester: str) -> int:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .eq("hebrew_year", hebrew_year)
        .eq("semester", semester)
        .is_("deleted_at", "null")
        .execute()
    )
    return resp.count or 0


def get_studied_figure_ids(recording_id: int) -> list[dict]:
    """Returns [{id, name}] for all studied figures linked to a recording."""
    sb = get_supabase()
    resp = (
        sb.table("recording_studied_figures")
        .select("figure_id, studied_figures(name)")
        .eq("recording_id", recording_id)
        .execute()
    )
    return [
        {"id": r["figure_id"], "name": r["studied_figures"]["name"]}
        for r in (resp.data or [])
        if r.get("studied_figures")
    ]


def get_recordings_by_studied_figure(figure_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recording_studied_figures")
        .select(f"recordings({_recording_select()})")
        .eq("figure_id", figure_id)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    rows = [r["recordings"] for r in (resp.data or []) if r.get("recordings")]
    return _flatten_joins(rows)


def count_by_studied_figure(figure_id: int) -> int:
    sb = get_supabase()
    resp = (
        sb.table("recording_studied_figures")
        .select("figure_id", count="exact", head=True)
        .eq("figure_id", figure_id)
        .execute()
    )
    return resp.count or 0


def get_recent_recordings(limit: int = 10) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return _flatten_joins(resp.data or [])


# ---------------------------------------------------------------------------
# Single record
# ---------------------------------------------------------------------------

def get_recording(recording_id: int) -> dict | None:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(
            _recording_select() + ", "
            "recording_tags(tag), recording_studied_figures(studied_figures(name))"
        )
        .eq("id", recording_id)
        .single()
        .execute()
    )
    if not resp.data:
        return None
    row = _flatten_joins([resp.data])[0]
    row["tags"] = [t["tag"] for t in (resp.data.get("recording_tags") or [])]
    row["studied_figures"] = [
        sf["studied_figures"]["name"]
        for sf in (resp.data.get("recording_studied_figures") or [])
        if sf.get("studied_figures")
    ]
    return row


def get_recording_by_message_id(message_id: int) -> dict | None:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(
            _recording_select() + ", "
            "recording_tags(tag), recording_studied_figures(studied_figures(name))"
        )
        .eq("message_id", message_id)
        .single()
        .execute()
    )
    if not resp.data:
        return None
    row = _flatten_joins([resp.data])[0]
    row["tags"] = [t["tag"] for t in (resp.data.get("recording_tags") or [])]
    row["studied_figures"] = [
        sf["studied_figures"]["name"]
        for sf in (resp.data.get("recording_studied_figures") or [])
        if sf.get("studied_figures")
    ]
    return row


# ---------------------------------------------------------------------------
# Admin review
# ---------------------------------------------------------------------------

def needs_review_next(skip_ids: list[int] | None = None) -> dict | None:
    sb = get_supabase()
    q = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("needs_human_review", True)
        .is_("deleted_at", "null")
        .order("date", desc=True)
        .limit(1)
    )
    if skip_ids:
        q = q.not_.in_("id", skip_ids)
    resp = q.execute()
    if not resp.data:
        return None
    return _flatten_joins(resp.data)[0]


def mark_reviewed(recording_id: int) -> None:
    sb = get_supabase()
    sb.table("recordings").update({"needs_human_review": False}).eq("id", recording_id).execute()


# ---------------------------------------------------------------------------
# Manage — update recording fields, soft delete
# ---------------------------------------------------------------------------

def get_recording_by_display_id(display_id: int) -> dict | None:
    """Fetch a non-deleted recording by its DB id (the #id shown to users)."""
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(
            _recording_select() + ", "
            "recording_tags(tag), recording_studied_figures(studied_figures(name))"
        )
        .eq("id", display_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not resp.data:
        return None
    row = _flatten_joins([resp.data])[0]
    row["tags"] = [t["tag"] for t in (resp.data.get("recording_tags") or [])]
    row["studied_figures"] = [
        sf["studied_figures"]["name"]
        for sf in (resp.data.get("recording_studied_figures") or [])
        if sf.get("studied_figures")
    ]
    return row


def update_recording_series(recording_id: int, series_id: int | None) -> None:
    sb = get_supabase()
    update = {"series_id": series_id}
    if series_id is None:
        update["lesson_number"] = None
    sb.table("recordings").update(update).eq("id", recording_id).execute()


def update_recording_teacher(recording_id: int, teacher_id: int | None) -> None:
    sb = get_supabase()
    sb.table("recordings").update({"teacher_id": teacher_id}).eq("id", recording_id).execute()


def update_recording_title(recording_id: int, title: str) -> None:
    sb = get_supabase()
    sb.table("recordings").update({"title": title}).eq("id", recording_id).execute()


def soft_delete_recording(recording_id: int) -> None:
    sb = get_supabase()
    from datetime import datetime, timezone
    sb.table("recordings").update({
        "deleted_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", recording_id).execute()


def delete_series_if_empty(series_id: int | None) -> bool:
    """Delete series if it has no non-deleted recordings. Returns True if deleted."""
    if not series_id:
        return False
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .eq("series_id", series_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if (resp.count or 0) == 0:
        # Nullify series_id on soft-deleted rows so FK doesn't block deletion
        sb.table("recordings").update({"series_id": None, "lesson_number": None}).eq("series_id", series_id).execute()
        sb.table("series").delete().eq("id", series_id).execute()
        return True
    return False


def delete_teacher_if_empty(teacher_id: int | None) -> bool:
    """Delete teacher if they have no non-deleted recordings. Returns True if deleted."""
    if not teacher_id:
        return False
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .eq("teacher_id", teacher_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if (resp.count or 0) == 0:
        # Nullify teacher_id on soft-deleted rows so FK doesn't block deletion
        sb.table("recordings").update({"teacher_id": None}).eq("teacher_id", teacher_id).execute()
        # Delete any series still referencing this teacher (FK would also block deletion)
        sb.table("series").update({"teacher_id": None}).eq("teacher_id", teacher_id).execute()
        sb.table("teachers").delete().eq("id", teacher_id).execute()
        return True
    return False


# ---------------------------------------------------------------------------
# Get-or-create helpers (for upload flow — resolve names to IDs)
# ---------------------------------------------------------------------------

def get_or_create_teacher(name: str) -> int:
    sb = get_supabase()
    resp = sb.table("teachers").select("id").eq("name", name).maybe_single().execute()
    if resp and resp.data:
        return resp.data["id"]
    sb.table("teachers").insert({"name": name}).execute()
    resp = sb.table("teachers").select("id").eq("name", name).maybe_single().execute()
    return resp.data["id"]


def get_or_create_series(name: str, teacher_id: int | None) -> int:
    sb = get_supabase()
    q = sb.table("series").select("id").eq("name", name)
    if teacher_id:
        q = q.eq("teacher_id", teacher_id)
    resp = q.maybe_single().execute()
    if resp and resp.data:
        return resp.data["id"]
    data: dict = {"name": name}
    if teacher_id:
        data["teacher_id"] = teacher_id
    sb.table("series").insert(data).execute()
    q = sb.table("series").select("id").eq("name", name)
    if teacher_id:
        q = q.eq("teacher_id", teacher_id)
    resp = q.maybe_single().execute()
    return resp.data["id"]


# ---------------------------------------------------------------------------
# Insert new recording (from upload flow)
# ---------------------------------------------------------------------------

def insert_new_recording(data: dict) -> dict:
    """Insert a new recording. Returns the inserted row with its id."""
    sb = get_supabase()
    resp = sb.table("recordings").insert(data).execute()
    return resp.data[0] if resp.data else {}


def insert_recording_tags(recording_id: int, tags: list[str]) -> None:
    sb = get_supabase()
    if tags:
        sb.table("recording_tags").insert(
            [{"recording_id": recording_id, "tag": t} for t in tags]
        ).execute()


# ---------------------------------------------------------------------------
# Helper: flatten Supabase nested join dicts into flat keys
# ---------------------------------------------------------------------------

def _flatten_joins(rows: list[dict]) -> list[dict]:
    """
    Supabase returns joined tables as nested dicts, e.g. {"teachers": {"name": "X"}}.
    Flatten to teacher_name, series_name, etc.
    """
    flat = []
    for row in rows:
        r = dict(row)
        for key in ("teachers", "series", "chavurot"):
            nested = r.pop(key, None)
            col = key.rstrip("s")  # teachers→teacher, series→series
            if key == "series":
                col = "series"
            r[f"{col}_name"] = nested["name"] if isinstance(nested, dict) else None
        flat.append(r)
    return flat


# ---------------------------------------------------------------------------
# User tracking + event log
# ---------------------------------------------------------------------------

def upsert_user(user_id: int, username: str | None) -> None:
    """Register or refresh a user on /start. Sets first_seen on insert, updates last_seen always."""
    from datetime import datetime, timezone
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    sb.table("bot_users").upsert(
        {"user_id": user_id, "username": username, "last_seen": now},
        on_conflict="user_id",
    ).execute()


def log_event(user_id: int, event_type: str, event_data: dict | None = None) -> None:
    """Append one row to user_events. Fire-and-forget — never raises."""
    try:
        get_supabase().table("user_events").insert({
            "user_id": user_id,
            "event_type": event_type,
            "event_data": event_data or {},
        }).execute()
    except Exception:
        pass


def get_stats() -> dict:
    """Aggregate statistics for the /stats admin command.

    Uses 3 HTTP calls total:
      1. get_all_stats() RPC  — all counts in one SQL query
      2. top_downloaded_recordings() RPC
      3. top_search_queries() RPC
    """
    from datetime import datetime, timezone
    sb = get_supabase()
    start_of_month = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    # All scalar counts in one round trip
    counts = sb.rpc("get_all_stats", {}).execute().data or {}

    top_downloads = (
        sb.rpc("top_downloaded_recordings", {
            "p_since": start_of_month,
            "p_limit": 5,
        }).execute().data or []
    )

    top_searches = (
        sb.rpc("top_search_queries", {
            "p_since": start_of_month,
            "p_limit": 5,
        }).execute().data or []
    )

    return {
        "total_users":      int(counts.get("total_users", 0)),
        "new_this_month":   int(counts.get("new_this_month", 0)),
        "new_this_week":    int(counts.get("new_this_week", 0)),
        "total_recordings": int(counts.get("total_recordings", 0)),
        "downloaded_to_r2": int(counts.get("downloaded_to_r2", 0)),
        "pending_review":   int(counts.get("pending_review", 0)),
        "dl_total":         int(counts.get("dl_total", 0)),
        "dl_today":         int(counts.get("dl_today", 0)),
        "dl_week":          int(counts.get("dl_week", 0)),
        "dl_month":         int(counts.get("dl_month", 0)),
        "search_total":     int(counts.get("search_total", 0)),
        "search_month":     int(counts.get("search_month", 0)),
        "upload_total":     int(counts.get("upload_total", 0)),
        "upload_month":     int(counts.get("upload_month", 0)),
        "top_downloads":    top_downloads,
        "top_searches":     top_searches,
    }
