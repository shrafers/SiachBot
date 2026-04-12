"""
Stage 4 import script — load tagged_recordings.json into Supabase.

Prerequisites:
  1. Run schema.sql in Supabase SQL editor first.
  2. Set SUPABASE_URL and SUPABASE_KEY in .env.

Usage:
  python import_to_supabase.py
"""

import json
import os
from collections import defaultdict

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tagged_recordings.json")
BATCH_SIZE = 100


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def upsert_and_fetch(sb: Client, table: str, rows: list[dict], conflict_col: str = "name") -> dict:
    """Upsert rows by name, then return {name: id} lookup dict."""
    if not rows:
        return {}
    for batch in chunks(rows, BATCH_SIZE):
        sb.table(table).upsert(batch, on_conflict=conflict_col).execute()
    result = sb.table(table).select("id, name").execute()
    return {r["name"]: r["id"] for r in result.data}


def main():
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    print(f"Loading {DATA_PATH}...")
    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)
    print(f"  {len(records)} records loaded.\n")

    # ------------------------------------------------------------------ #
    # Phase 1 — collect unique values from JSON
    # ------------------------------------------------------------------ #
    teachers_set = set()
    subject_areas_set = set()
    sub_disciplines_set = set()   # (name, subject_area) pairs
    chavurot_set = set()
    studied_figures_set = set()
    # series: {name: {teacher, subject_area, lesson_count}}
    series_map: dict[str, dict] = {}

    for r in records:
        if r.get("teacher"):
            teachers_set.add(r["teacher"])
        if r.get("subject_area"):
            subject_areas_set.add(r["subject_area"])
        if r.get("sub_discipline"):
            sub_disciplines_set.add((r["sub_discipline"], r.get("subject_area")))
        if r.get("chavura"):
            chavurot_set.add(r["chavura"])
        for fig in r.get("studied_figures") or []:
            if fig:
                studied_figures_set.add(fig)
        sn = r.get("series_name")
        if sn:
            if sn not in series_map:
                series_map[sn] = {
                    "teacher": r.get("teacher"),
                    "subject_area": r.get("subject_area"),
                    "lesson_count": 0,
                }
            series_map[sn]["lesson_count"] += 1

    # ------------------------------------------------------------------ #
    # Phase 2 — insert reference tables
    # ------------------------------------------------------------------ #
    print("[1/8] Inserting teachers...")
    teacher_lookup = upsert_and_fetch(sb, "teachers", [{"name": n} for n in sorted(teachers_set)])
    print(f"  {len(teacher_lookup)} teachers.")

    print("[2/8] Inserting subject_areas...")
    subject_area_lookup = upsert_and_fetch(sb, "subject_areas", [{"name": n} for n in sorted(subject_areas_set)])
    print(f"  {len(subject_area_lookup)} subject areas.")

    print("[3/8] Inserting sub_disciplines...")
    # Deduplicate by name (same discipline may appear with different subject areas)
    sub_disc_by_name: dict[str, dict] = {}
    for name, sa in sub_disciplines_set:
        if name not in sub_disc_by_name:
            row: dict = {"name": name}
            if sa and sa in subject_area_lookup:
                row["subject_area_id"] = subject_area_lookup[sa]
            sub_disc_by_name[name] = row
    sub_discipline_lookup = upsert_and_fetch(sb, "sub_disciplines", list(sub_disc_by_name.values()))
    print(f"  {len(sub_discipline_lookup)} sub-disciplines.")

    print("[4/8] Inserting chavurot...")
    chavura_lookup = upsert_and_fetch(sb, "chavurot", [{"name": n} for n in sorted(chavurot_set)])
    print(f"  {len(chavura_lookup)} chavurot.")

    print("[5/8] Inserting studied_figures...")
    figure_lookup = upsert_and_fetch(sb, "studied_figures", [{"name": n} for n in sorted(studied_figures_set)])
    print(f"  {len(figure_lookup)} studied figures.")

    print("[6/8] Inserting series...")
    series_rows = []
    for name, info in series_map.items():
        row: dict = {"name": name, "total_lessons": info["lesson_count"]}
        if info["teacher"] and info["teacher"] in teacher_lookup:
            row["teacher_id"] = teacher_lookup[info["teacher"]]
        if info["subject_area"] and info["subject_area"] in subject_area_lookup:
            row["subject_area_id"] = subject_area_lookup[info["subject_area"]]
        series_rows.append(row)
    series_lookup = upsert_and_fetch(sb, "series", series_rows)
    print(f"  {len(series_lookup)} series.")

    # ------------------------------------------------------------------ #
    # Phase 3 — insert recordings
    # ------------------------------------------------------------------ #
    print("[7/8] Inserting recordings...")
    recording_rows = []
    for r in records:
        row: dict = {
            "message_id": r["message_id"],
            "date": r.get("date"),
            "hebrew_date": r.get("hebrew_date"),
            "semester": r.get("semester"),
            "filename": r.get("filename"),
            "title": r.get("title"),
            "lesson_number": r.get("lesson_number"),
            "is_oneoff": bool(r.get("is_oneoff", False)),
            "duration_seconds": r.get("duration_seconds"),
            "file_size_bytes": r.get("file_size_bytes"),
            "telegram_link": r.get("telegram_link"),
            "audio_downloaded": bool(r.get("audio_downloaded", False)),
            "audio_r2_path": r.get("audio_r2_path"),
            "confidence": r.get("confidence"),
            "needs_human_review": bool((r.get("quality_flags") or {}).get("needs_human_review", False)),
            "tagged_by": "claude",
        }
        if r.get("teacher") and r["teacher"] in teacher_lookup:
            row["teacher_id"] = teacher_lookup[r["teacher"]]
        if r.get("subject_area") and r["subject_area"] in subject_area_lookup:
            row["subject_area_id"] = subject_area_lookup[r["subject_area"]]
        if r.get("sub_discipline") and r["sub_discipline"] in sub_discipline_lookup:
            row["sub_discipline_id"] = sub_discipline_lookup[r["sub_discipline"]]
        if r.get("series_name") and r["series_name"] in series_lookup:
            row["series_id"] = series_lookup[r["series_name"]]
        if r.get("chavura") and r["chavura"] in chavura_lookup:
            row["chavura_id"] = chavura_lookup[r["chavura"]]
        recording_rows.append(row)

    inserted = 0
    errors = 0
    for batch in chunks(recording_rows, BATCH_SIZE):
        try:
            sb.table("recordings").upsert(batch, on_conflict="message_id").execute()
            inserted += len(batch)
        except Exception as e:
            print(f"  ERROR inserting batch: {e}")
            errors += 1
    print(f"  {inserted} recordings upserted, {errors} batch errors.")

    # Build message_id → db id lookup for junction tables
    print("  Fetching recording IDs for junction inserts...")
    all_recordings = sb.table("recordings").select("id, message_id, date, teacher_id, duration_seconds, needs_human_review").execute().data
    msg_to_id = {r["message_id"]: r["id"] for r in all_recordings}

    # ------------------------------------------------------------------ #
    # Phase 4 — junction tables
    # ------------------------------------------------------------------ #
    print("[8/8] Inserting junction rows (studied_figures, tags)...")
    figure_junction_rows = []
    tag_rows = []

    for r in records:
        rec_id = msg_to_id.get(r["message_id"])
        if rec_id is None:
            continue
        for fig in r.get("studied_figures") or []:
            if fig and fig in figure_lookup:
                figure_junction_rows.append({"recording_id": rec_id, "figure_id": figure_lookup[fig]})
        for tag in r.get("thematic_tags") or []:
            if tag:
                tag_rows.append({"recording_id": rec_id, "tag": tag})

    fig_inserted = 0
    for batch in chunks(figure_junction_rows, BATCH_SIZE):
        try:
            sb.table("recording_studied_figures").upsert(batch).execute()
            fig_inserted += len(batch)
        except Exception as e:
            print(f"  ERROR inserting figure junction batch: {e}")

    tag_inserted = 0
    for batch in chunks(tag_rows, BATCH_SIZE):
        try:
            sb.table("recording_tags").upsert(batch).execute()
            tag_inserted += len(batch)
        except Exception as e:
            print(f"  ERROR inserting tag batch: {e}")

    print(f"  {fig_inserted} studied-figure links, {tag_inserted} tags.")

    # ------------------------------------------------------------------ #
    # Phase 5 — deduplication pass
    # ------------------------------------------------------------------ #
    print("\nDeduplication pass...")
    # Group by (date, teacher_id) — find recordings with duration within ±60s
    groups: dict[tuple, list] = defaultdict(list)
    for r in all_recordings:
        key = (r["date"], r["teacher_id"])
        groups[key].append(r)

    dup_ids = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        group_sorted = sorted(group, key=lambda x: x["id"])
        for i, a in enumerate(group_sorted):
            for b in group_sorted[i + 1 :]:
                dur_a = a.get("duration_seconds") or 0
                dur_b = b.get("duration_seconds") or 0
                if abs(dur_a - dur_b) <= 60:
                    # Mark the later one (higher id) as needing review
                    dup_ids.append(b["id"])

    if dup_ids:
        dup_ids = list(set(dup_ids))
        for batch in chunks(dup_ids, BATCH_SIZE):
            sb.table("recordings").update({"needs_human_review": True}).in_("id", batch).execute()
        print(f"  Flagged {len(dup_ids)} duplicate recordings for review.")
    else:
        print("  No duplicates found.")

    # ------------------------------------------------------------------ #
    # Phase 6 — validation pass (null title AND null teacher)
    # ------------------------------------------------------------------ #
    print("Validation pass (null title + null teacher)...")
    null_both = sb.table("recordings").select("id").is_("title", "null").is_("teacher_id", "null").execute().data
    null_ids = [r["id"] for r in null_both]
    if null_ids:
        for batch in chunks(null_ids, BATCH_SIZE):
            sb.table("recordings").update({"needs_human_review": True}).in_("id", batch).execute()
        print(f"  Flagged {len(null_ids)} recordings with no title and no teacher.")
    else:
        print("  All recordings have at least a title or teacher.")

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    print("\n=== Import complete ===")
    counts = {
        "teachers": sb.table("teachers").select("id", count="exact").execute().count,
        "subject_areas": sb.table("subject_areas").select("id", count="exact").execute().count,
        "sub_disciplines": sb.table("sub_disciplines").select("id", count="exact").execute().count,
        "series": sb.table("series").select("id", count="exact").execute().count,
        "chavurot": sb.table("chavurot").select("id", count="exact").execute().count,
        "studied_figures": sb.table("studied_figures").select("id", count="exact").execute().count,
        "recordings": sb.table("recordings").select("id", count="exact").execute().count,
        "needs_human_review": sb.table("recordings").select("id", count="exact").eq("needs_human_review", True).execute().count,
    }
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
