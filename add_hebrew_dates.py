"""
Add Hebrew dates and semesters to tagged_recordings.json.

Semesters:
  אלול  — 1 Elul (month 6) through end of Tishrei (month 7)
  חורף  — 1 Cheshvan (month 8) through end of Nisan (month 1)
  קיץ   — 1 Iyar (month 2) through end of Av (month 5)
"""

import json
from datetime import date
from pyluach import dates

INPUT_FILE = "data/tagged_recordings.json"
OUTPUT_FILE = "data/tagged_recordings.json"

HEBREW_MONTHS = {
    1: "ניסן",
    2: "אייר",
    3: "סיון",
    4: "תמוז",
    5: "אב",
    6: "אלול",
    7: "תשרי",
    8: "חשוון",
    9: "כסלו",
    10: "טבת",
    11: "שבט",
    12: "אדר",
    13: "אדר ב׳",
}

HEBREW_DIGITS = {
    1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה", 6: "ו", 7: "ז", 8: "ח", 9: "ט",
    10: "י", 11: "יא", 12: "יב", 13: "יג", 14: "יד", 15: "טו", 16: "טז",
    17: "יז", 18: "יח", 19: "יט", 20: "כ", 21: "כא", 22: "כב", 23: "כג",
    24: "כד", 25: "כה", 26: "כו", 27: "כז", 28: "כח", 29: "כט", 30: "ל",
}

def hebrew_day_str(day: int) -> str:
    return HEBREW_DIGITS.get(day, str(day))

def format_hebrew_year(year: int) -> str:
    """Convert a Hebrew year (e.g. 5780) to gematria short form (e.g. תש״פ)."""
    # pyluach's built-in string includes the year nicely
    # We'll just pull the year portion from hebrew_date_string
    return None  # will use pyluach directly

def get_hebrew_date_string(hdate) -> str:
    """Return e.g. 'ו אלול תש״פ' (no geresh after day)."""
    day = hebrew_day_str(hdate.day)
    month = HEBREW_MONTHS[hdate.month]
    # Get the year gematria from pyluach's own string (last word)
    full = hdate.hebrew_date_string()  # e.g. "ו׳ אלול תש״פ"
    year_gematria = full.split()[-1]   # "תש״פ"
    return f"{day} {month} {year_gematria}"

def get_semester(hdate) -> str:
    """Return Hebrew semester name for a given Hebrew date."""
    m = hdate.month
    # Elul (6) and Tishrei (7)
    if m in (6, 7):
        return "אלול"
    # Iyar (2) through Av (5)
    if 2 <= m <= 5:
        return "קיץ"
    # Cheshvan (8) through Nisan (1): months 8,9,10,11,12,13 and 1
    return "חורף"

def process():
    with open(INPUT_FILE, encoding="utf-8") as f:
        recordings = json.load(f)

    updated = 0
    for rec in recordings:
        raw_date = rec.get("date")
        if not raw_date:
            rec["hebrew_date"] = None
            rec["semester"] = None
            continue

        try:
            parts = raw_date.split("-")
            greg = date(int(parts[0]), int(parts[1]), int(parts[2]))
            hdate = dates.HebrewDate.from_pydate(greg)
            rec["hebrew_date"] = get_hebrew_date_string(hdate)
            rec["semester"] = get_semester(hdate)
            updated += 1
        except Exception as e:
            print(f"Warning: could not convert date '{raw_date}' for message {rec.get('message_id')}: {e}")
            rec["hebrew_date"] = None
            rec["semester"] = None

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(recordings, f, ensure_ascii=False, indent=2)

    print(f"Done. Updated {updated}/{len(recordings)} records.")

if __name__ == "__main__":
    process()
