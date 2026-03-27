"""Supabase query layer — all DB interactions live here."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

PAGE_SIZE = 5   # results per page for recordings
LIST_SIZE = 10  # items per page for browse lists


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_recordings(query: str, page: int = 0, filter_type: str = "all") -> list[dict]:
    """
    Full-text search across title, teacher, series, sub_discipline, tags, studied_figures.
    filter_type: 'all' | 'series' | 'oneoff'
    Returns enriched rows with joined names.
    """
    sb = get_supabase()
    offset = page * PAGE_SIZE

    # Build base query with joins via select
    q = (
        sb.table("recordings")
        .select(
            "id, message_id, title, date, hebrew_date, is_oneoff, "
            "audio_downloaded, audio_r2_path, telegram_link, lesson_number, duration_seconds, "
            "teachers(name), series(name), chavurot(name)"
        )
        .text_search("title", query, config="simple")
        .order("date", desc=True)
        .range(offset, offset + PAGE_SIZE - 1)
    )

    if filter_type == "series":
        q = q.not_.is_("series_id", "null")
    elif filter_type == "oneoff":
        q = q.eq("is_oneoff", True)

    resp = q.execute()
    return _flatten_joins(resp.data or [])


def count_search(query: str, filter_type: str = "all") -> int:
    """Return total hit count for pagination."""
    sb = get_supabase()
    q = (
        sb.table("recordings")
        .select("id", count="exact", head=True)
        .text_search("title", query, config="simple")
    )
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
        .execute()
    )
    return resp.count or 0


def get_recent_by_teacher(teacher_id: int, limit: int = 10) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("teacher_id", teacher_id)
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
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_teacher(teacher_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("teacher_id", teacher_id).execute()
    return resp.count or 0


def get_recordings_by_series(series_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("series_id", series_id)
        .order("lesson_number", desc=False, nullsfirst=False)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_series(series_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("series_id", series_id).execute()
    return resp.count or 0


def get_recordings_by_chavura(chavura_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("chavura_id", chavura_id)
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_chavura(chavura_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("chavura_id", chavura_id).execute()
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
        .order("created_at", desc=True)
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
# Get-or-create helpers (for upload flow — resolve names to IDs)
# ---------------------------------------------------------------------------

def get_or_create_teacher(name: str) -> int:
    sb = get_supabase()
    resp = sb.table("teachers").select("id").eq("name", name).maybe_single().execute()
    if resp.data:
        return resp.data["id"]
    resp = sb.table("teachers").insert({"name": name}).select("id").execute()
    return resp.data[0]["id"]


def get_or_create_series(name: str, teacher_id: int | None) -> int:
    sb = get_supabase()
    # Uniqueness is now per (name, teacher_id)
    q = sb.table("series").select("id").eq("name", name)
    if teacher_id:
        q = q.eq("teacher_id", teacher_id)
    resp = q.maybe_single().execute()
    if resp.data:
        return resp.data["id"]
    data: dict = {"name": name}
    if teacher_id:
        data["teacher_id"] = teacher_id
    resp = sb.table("series").insert(data).select("id").execute()
    return resp.data[0]["id"]


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
