"""Formatting helpers and callback data encoding."""

import json
import math


# ---------------------------------------------------------------------------
# Callback data — compact JSON, must stay ≤ 64 bytes (Telegram limit)
# ---------------------------------------------------------------------------

def encode_cb(action: str, **kwargs) -> str:
    payload = {"a": action, **kwargs}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(data.encode()) > 64:
        raise ValueError(f"Callback data too long ({len(data.encode())} bytes): {data}")
    return data


def decode_cb(data: str) -> dict:
    return json.loads(data)


# ---------------------------------------------------------------------------
# Result card formatting
# ---------------------------------------------------------------------------

def format_result_card(rec: dict) -> str:
    """Build a single result card as Markdown text."""
    lines = []

    title = rec.get("title") or rec.get("filename") or "ללא כותרת"
    lines.append(f"📖 *{_esc(title)}*")

    parts = []
    teacher = rec.get("teacher_name") or rec.get("teachers_name")
    if teacher:
        parts.append(f"👤 {_esc(teacher)}")

    series = rec.get("series_name") or rec.get("series_name")
    lesson = rec.get("lesson_number")
    if series:
        s = f"📚 {_esc(series)}"
        if lesson:
            s += f" — שיעור {lesson}"
        parts.append(s)
    elif rec.get("is_oneoff"):
        parts.append("📌 שיעור בודד")

    date = rec.get("hebrew_date") or rec.get("date") or ""
    if date:
        parts.append(f"📅 {_esc(str(date))}")

    if parts:
        lines.append("  |  ".join(parts))

    tags = rec.get("tags") or []
    figures = rec.get("studied_figures") or []
    all_tags = list(dict.fromkeys(tags + figures))  # dedupe, preserve order
    if all_tags:
        lines.append("🏷 " + ", ".join(_esc(t) for t in all_tags[:5]))

    duration = rec.get("duration_seconds")
    if duration:
        lines.append(f"⏱ {format_duration(duration)}")

    if rec.get("confidence") == "low":
        lines.append("⚠️ _מידע לא מאומת_")

    return "\n".join(lines)


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))


def _esc(text: str) -> str:
    """Escape Markdown v1 special chars."""
    for ch in r"_*`[":
        text = text.replace(ch, f"\\{ch}")
    return text
