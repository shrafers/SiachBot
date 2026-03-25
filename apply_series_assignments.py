#!/usr/bin/env python3
"""
Apply series_assignments.csv to Supabase.
- Rows with new_series set → assign to that series (create if needed)
- Rows with empty new_series → assign to "שיעורים חד פעמיים" per teacher
"""

import csv
import os
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

CSV_PATH = "/Users/hillellewin/Downloads/series_assignments.csv"
ONE_OFF_NAME = "שיעורים חד פעמיים"

# ── Load CSV ─────────────────────────────────────────────────────────────────
with open(CSV_PATH, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"Loaded {len(rows)} rows from CSV")

# ── Load teacher lookup ───────────────────────────────────────────────────────
teachers_res = sb.table("teachers").select("id, name").execute()
teacher_id = {r["name"]: r["id"] for r in teachers_res.data}
print(f"Loaded {len(teacher_id)} teachers")

# ── Determine target series for each row ────────────────────────────────────
# Fill empty new_series with ONE_OFF_NAME
for row in rows:
    if not row["new_series"].strip():
        row["new_series"] = ONE_OFF_NAME

# ── Collect all (teacher, series_name) pairs we need ────────────────────────
needed = set()
for row in rows:
    needed.add((row["teacher"], row["new_series"]))

print(f"Need {len(needed)} unique (teacher, series) pairs")

# ── Load existing series ──────────────────────────────────────────────────────
existing_res = sb.table("series").select("id, name, teacher_id").execute()
# key: (name, teacher_id) → series_id
series_map = {(r["name"], r["teacher_id"]): r["id"] for r in existing_res.data}
print(f"Existing series in DB: {len(series_map)}")

# ── Create missing series ─────────────────────────────────────────────────────
created = 0
for (teacher_name, series_name) in sorted(needed):
    tid = teacher_id.get(teacher_name)
    if tid is None:
        print(f"  ⚠️  Unknown teacher: {teacher_name!r} — skipping")
        continue
    if (series_name, tid) not in series_map:
        res = sb.table("series").insert({"name": series_name, "teacher_id": tid}).execute()
        new_id = res.data[0]["id"]
        series_map[(series_name, tid)] = new_id
        created += 1
        print(f"  ➕ Created series: {series_name!r} for {teacher_name!r} (id={new_id})")

print(f"Created {created} new series")

# ── Build update batches ──────────────────────────────────────────────────────
updates = []  # list of (message_id, series_id)
skipped = 0

for row in rows:
    msg_id = int(row["message_id"])
    teacher_name = row["teacher"]
    new_series = row["new_series"]
    old_series = row["old_series"]

    tid = teacher_id.get(teacher_name)
    if tid is None:
        skipped += 1
        continue

    sid = series_map.get((new_series, tid))
    if sid is None:
        print(f"  ⚠️  No series id for ({new_series!r}, {teacher_name!r}) — skipping msg {msg_id}")
        skipped += 1
        continue

    updates.append((msg_id, sid))

print(f"\nApplying {len(updates)} updates ({skipped} skipped)...")

# ── Apply updates in batches ──────────────────────────────────────────────────
BATCH = 50
errors = 0
for i in range(0, len(updates), BATCH):
    batch = updates[i:i+BATCH]
    for msg_id, sid in batch:
        try:
            sb.table("recordings").update({"series_id": sid}).eq("message_id", msg_id).execute()
        except Exception as e:
            print(f"  ❌ Error on message_id={msg_id}: {e}")
            errors += 1
    done = min(i + BATCH, len(updates))
    print(f"  {done}/{len(updates)}", end="\r")

print(f"\n✅ Done. {len(updates) - errors} updated, {errors} errors, {skipped} skipped.")

# ── Summary ───────────────────────────────────────────────────────────────────
res = sb.table("recordings").select("series_id", count="exact").is_("series_id", "null").execute()
print(f"\nRecordings still without series: {res.count}")
res2 = sb.table("recordings").select("series_id", count="exact").not_.is_("series_id", "null").execute()
print(f"Recordings with series: {res2.count}")
