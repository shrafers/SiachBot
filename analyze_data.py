#!/usr/bin/env python3
"""Quick statistics analysis of tagged_recordings.json"""

import json
from collections import Counter, defaultdict

with open("data/tagged_recordings.json", encoding="utf-8") as f:
    data = json.load(f)

total = len(data)
print(f"{'='*60}")
print(f"TOTAL RECORDINGS: {total}")
print(f"{'='*60}\n")

# Teachers
teachers = [r.get("teacher") for r in data if r.get("teacher")]
teacher_counts = Counter(teachers)
print(f"TEACHERS ({len(teacher_counts)} unique):")
for teacher, count in teacher_counts.most_common():
    print(f"  {teacher}: {count}")

print()

# Subject areas
subjects = [r.get("subject_area") for r in data if r.get("subject_area")]
subject_counts = Counter(subjects)
print(f"SUBJECT AREAS ({len(subject_counts)} unique):")
for subject, count in subject_counts.most_common():
    print(f"  {subject}: {count}")

print()

# Sub-disciplines
subdiscs = [r.get("sub_discipline") for r in data if r.get("sub_discipline")]
subdisc_counts = Counter(subdiscs)
print(f"SUB-DISCIPLINES ({len(subdisc_counts)} unique):")
for s, count in subdisc_counts.most_common():
    print(f"  {s}: {count}")

print()

# Chavura
chavura_recordings = [r for r in data if r.get("chavura")]
chavura_counts = Counter(r["chavura"] for r in chavura_recordings)
print(f"CHAVURA RECORDINGS: {len(chavura_recordings)} total ({len(chavura_counts)} different chavurot)")
for c, count in chavura_counts.most_common():
    print(f"  {c}: {count}")

print()

# One-offs vs series
oneoffs = [r for r in data if r.get("is_oneoff") is True]
in_series = [r for r in data if r.get("is_oneoff") is False]
print(f"ONE-OFFS: {len(oneoffs)}")
print(f"IN SERIES: {len(in_series)}")

print()

# Series analysis
series_counts = Counter(r.get("series_name") for r in data if r.get("series_name") and not r.get("is_oneoff"))
print(f"SERIES ({len(series_counts)} unique):")
for series, count in series_counts.most_common(20):
    print(f"  {series}: {count} lessons")
if len(series_counts) > 20:
    print(f"  ... and {len(series_counts) - 20} more series")

print()

# Thematic tags
all_tags = []
for r in data:
    all_tags.extend(r.get("thematic_tags") or [])
tag_counts = Counter(all_tags)
recordings_with_tags = sum(1 for r in data if r.get("thematic_tags"))
print(f"THEMATIC TAGS: {len(all_tags)} total, {len(tag_counts)} unique, across {recordings_with_tags} recordings")
print("Top 30 tags:")
for tag, count in tag_counts.most_common(30):
    print(f"  {tag}: {count}")

print()

# Studied figures
all_figures = []
for r in data:
    all_figures.extend(r.get("studied_figures") or [])
figure_counts = Counter(all_figures)
print(f"STUDIED FIGURES: {len(all_figures)} total, {len(figure_counts)} unique")
for fig, count in figure_counts.most_common(20):
    print(f"  {fig}: {count}")

print()

# Confidence
confidence_counts = Counter(r.get("confidence") for r in data)
print(f"CONFIDENCE LEVELS:")
for level, count in confidence_counts.most_common():
    print(f"  {level}: {count}")

print()

# Quality flags
missing_teacher = sum(1 for r in data if r.get("quality_flags", {}).get("missing_teacher"))
missing_topic = sum(1 for r in data if r.get("quality_flags", {}).get("missing_topic"))
needs_review = sum(1 for r in data if r.get("quality_flags", {}).get("needs_human_review"))
print(f"QUALITY FLAGS:")
print(f"  Missing teacher: {missing_teacher}")
print(f"  Missing topic: {missing_topic}")
print(f"  Needs human review: {needs_review}")

print()

# Date range
dates = sorted(r["date"] for r in data if r.get("date"))
print(f"DATE RANGE: {dates[0]} → {dates[-1]}")

# Duration stats
durations = [r["duration_seconds"] for r in data if r.get("duration_seconds")]
if durations:
    avg_min = sum(durations) / len(durations) / 60
    total_hours = sum(durations) / 3600
    print(f"DURATION: avg {avg_min:.1f} min, total {total_hours:.1f} hours")
