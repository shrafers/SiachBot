#!/usr/bin/env python3
"""Export full lists from tagged_recordings.json to a txt file."""

import json
from collections import Counter

with open("data/tagged_recordings.json", encoding="utf-8") as f:
    data = json.load(f)

lines = []

def section(title):
    lines.append("")
    lines.append("=" * 60)
    lines.append(title)
    lines.append("=" * 60)

# Teachers
teacher_counts = Counter(r.get("teacher") for r in data if r.get("teacher"))
section(f"TEACHERS ({len(teacher_counts)} unique)")
for teacher, count in teacher_counts.most_common():
    lines.append(f"  {teacher}: {count}")

# Subject areas
subject_counts = Counter(r.get("subject_area") for r in data if r.get("subject_area"))
section(f"SUBJECT AREAS ({len(subject_counts)} unique)")
for s, count in subject_counts.most_common():
    lines.append(f"  {s}: {count}")

# Sub-disciplines
subdisc_counts = Counter(r.get("sub_discipline") for r in data if r.get("sub_discipline"))
section(f"SUB-DISCIPLINES ({len(subdisc_counts)} unique)")
for s, count in subdisc_counts.most_common():
    lines.append(f"  {s}: {count}")

# Chavurot
chavura_recordings = [r for r in data if r.get("chavura")]
chavura_counts = Counter(r["chavura"] for r in chavura_recordings)
section(f"CHAVUROT ({len(chavura_counts)} unique, {len(chavura_recordings)} total recordings)")
for c, count in chavura_counts.most_common():
    lines.append(f"  {c}: {count}")

# Series
series_counts = Counter(r.get("series_name") for r in data if r.get("series_name") and not r.get("is_oneoff"))
section(f"SERIES ({len(series_counts)} unique)")
for s, count in series_counts.most_common():
    lines.append(f"  {s}: {count} lessons")

# One-offs
oneoffs = [r for r in data if r.get("is_oneoff") is True]
section(f"ONE-OFF RECORDINGS ({len(oneoffs)} total)")
for r in sorted(oneoffs, key=lambda x: x.get("date", "")):
    teacher = r.get("teacher", "לא ידוע")
    title = r.get("title", r.get("filename", ""))
    date = r.get("date", "")
    lines.append(f"  [{date}] {teacher} — {title}")

# Thematic tags
all_tags = []
for r in data:
    all_tags.extend(r.get("thematic_tags") or [])
tag_counts = Counter(all_tags)
section(f"THEMATIC TAGS ({len(tag_counts)} unique, {len(all_tags)} total uses)")
for tag, count in tag_counts.most_common():
    lines.append(f"  {tag}: {count}")

# Studied figures
all_figures = []
for r in data:
    all_figures.extend(r.get("studied_figures") or [])
figure_counts = Counter(all_figures)
section(f"STUDIED FIGURES ({len(figure_counts)} unique, {len(all_figures)} total mentions)")
for fig, count in figure_counts.most_common():
    lines.append(f"  {fig}: {count}")

# Missing teacher
missing_teacher = [r for r in data if r.get("quality_flags", {}).get("missing_teacher")]
section(f"MISSING TEACHER ({len(missing_teacher)} recordings)")
for r in sorted(missing_teacher, key=lambda x: x.get("date", "")):
    date = r.get("date", "")
    filename = r.get("filename", "")
    title = r.get("title", "")
    msg_id = r.get("message_id", "")
    lines.append(f"  [{date}] msg#{msg_id} — {title or filename}")

# Needs human review
needs_review = [r for r in data if r.get("quality_flags", {}).get("needs_human_review")]
section(f"NEEDS HUMAN REVIEW ({len(needs_review)} recordings)")
for r in sorted(needs_review, key=lambda x: x.get("date", "")):
    teacher = r.get("teacher", "לא ידוע")
    title = r.get("title", r.get("filename", ""))
    date = r.get("date", "")
    msg_id = r.get("message_id", "")
    confidence = r.get("confidence", "")
    lines.append(f"  [{date}] msg#{msg_id} [{confidence}] {teacher} — {title}")

# Low confidence
low_conf = [r for r in data if r.get("confidence") == "low"]
section(f"LOW CONFIDENCE ({len(low_conf)} recordings)")
for r in sorted(low_conf, key=lambda x: x.get("date", "")):
    teacher = r.get("teacher", "לא ידוע")
    title = r.get("title", r.get("filename", ""))
    date = r.get("date", "")
    msg_id = r.get("message_id", "")
    lines.append(f"  [{date}] msg#{msg_id} {teacher} — {title}")

output = "\n".join(lines)
with open("data/full_lists.txt", "w", encoding="utf-8") as f:
    f.write(output)

print(f"Written to data/full_lists.txt ({len(lines)} lines)")
