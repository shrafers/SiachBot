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
            "teachers(name), series(name), sub_disciplines(name), chavurot(name)"
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
    sb = get_supabase()
    resp = (
        sb.table("series")
        .select("id, name, total_lessons, teachers(name)")
        .order("name")
        .range(page * LIST_SIZE, page * LIST_SIZE + LIST_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_series() -> int:
    sb = get_supabase()
    resp = sb.table("series").select("id", count="exact", head=True).execute()
    return resp.count or 0


def get_subject_areas() -> list[dict]:
    sb = get_supabase()
    resp = sb.rpc("subject_areas_with_count").execute()
    return resp.data or []


def get_sub_disciplines(subject_area_id: int) -> list[dict]:
    """Sub-disciplines for a subject area with count >= 5 first, then 'אחר'."""
    sb = get_supabase()
    resp = sb.rpc("sub_disciplines_with_count", {"p_subject_area_id": subject_area_id}).execute()
    return resp.data or []


def get_chavurot() -> list[dict]:
    sb = get_supabase()
    resp = sb.rpc("chavurot_with_count").execute()
    return resp.data or []


def get_subject_areas_by_teacher(teacher_id: int) -> list[dict]:
    """Subject areas that have recordings for a specific teacher, with counts."""
    sb = get_supabase()
    resp = sb.rpc("subject_areas_by_teacher", {"p_teacher_id": teacher_id}).execute()
    return resp.data or []


def get_sub_disciplines_by_teacher_and_subject(teacher_id: int, subject_area_id: int) -> list[dict]:
    """Sub-disciplines with recordings for a specific teacher + subject area."""
    sb = get_supabase()
    resp = sb.rpc("sub_disciplines_by_teacher_and_subject", {
        "p_teacher_id": teacher_id,
        "p_subject_area_id": subject_area_id,
    }).execute()
    return resp.data or []


def get_recent_by_subject_area(subject_area_id: int, limit: int = 10) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("subject_area_id", subject_area_id)
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return _flatten_joins(resp.data or [])


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
        "audio_downloaded, audio_r2_path, telegram_link, lesson_number, duration_seconds, "
        "teachers(name), series(name), sub_disciplines(name), chavurot(name)"
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


def get_recordings_by_sub_discipline(sub_discipline_id: int, page: int = 0) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("recordings")
        .select(_recording_select())
        .eq("sub_discipline_id", sub_discipline_id)
        .order("date", desc=True)
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
        .execute()
    )
    return _flatten_joins(resp.data or [])


def count_by_sub_discipline(sub_discipline_id: int) -> int:
    sb = get_supabase()
    resp = sb.table("recordings").select("id", count="exact", head=True).eq("sub_discipline_id", sub_discipline_id).execute()
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
        for key in ("teachers", "series", "sub_disciplines", "chavurot"):
            nested = r.pop(key, None)
            col = key.rstrip("s")  # teachers→teacher, series→series, sub_disciplines→sub_discipline
            if key == "sub_disciplines":
                col = "sub_discipline"
            elif key == "series":
                col = "series"
            r[f"{col}_name"] = nested["name"] if isinstance(nested, dict) else None
        flat.append(r)
    return flat
