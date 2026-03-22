"""
One-time script: populate hebrew_year column in recordings table.

Computes the Hebrew year gematria from each recording's Gregorian date
using pyluach (already a project dependency). Safe to re-run — skips
rows that already have a hebrew_year value.

Usage:
  python backfill_hebrew_year.py
"""

import os
from datetime import date

from dotenv import load_dotenv
from pyluach import dates
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


def get_hebrew_year(greg_date_str: str) -> str | None:
    """Return Hebrew year gematria (e.g. 'תשפ״ה') from a Gregorian date string 'YYYY-MM-DD'."""
    try:
        parts = greg_date_str.split("-")
        greg = date(int(parts[0]), int(parts[1]), int(parts[2]))
        hdate = dates.HebrewDate.from_pydate(greg)
        full = hdate.hebrew_date_string()   # e.g. "ו׳ אלול תש״פ"
        return full.split()[-1]             # last word = year gematria
    except Exception as e:
        print(f"  Warning: could not convert date '{greg_date_str}': {e}")
        return None


def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = (
        sb.table("recordings")
        .select("id, date, hebrew_year")
        .not_.is_("date", "null")
        .execute()
    )
    rows = result.data or []
    to_update = [r for r in rows if not r.get("hebrew_year")]
    already_have = len(rows) - len(to_update)

    print(f"Total with date:   {len(rows)}")
    print(f"Already have year: {already_have}")
    print(f"Need backfill:     {len(to_update)}\n")

    succeeded = 0
    failed = 0

    for i, rec in enumerate(to_update, start=1):
        year = get_hebrew_year(rec["date"])
        if not year:
            failed += 1
            continue
        sb.table("recordings").update({"hebrew_year": year}).eq("id", rec["id"]).execute()
        print(f"[{i}/{len(to_update)}] id={rec['id']}  {rec['date']} → {year}")
        succeeded += 1

    print(f"\n=== Done ===")
    print(f"  Updated: {succeeded}")
    print(f"  Errors:  {failed}")


if __name__ == "__main__":
    main()
