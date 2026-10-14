#!/usr/bin/env python3
"""NUS regular-semester status for Waybar; no third-party dependencies.

Verified AY2026/27: https://nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf
Later cycles repeat this pattern (estimated), using the first Monday of August
for orientation and the second Monday of January for Semester 2.
Special terms are treated as vacation from regular semesters.
"""

import argparse
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SOURCE = "https://nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf"
VERIFIED_STARTS = {(2026, 1): date(2026, 8, 10), (2026, 2): date(2027, 1, 11)}


def first_monday(year, month):
    first = date(year, month, 1)
    return first + timedelta(days=(-first.weekday()) % 7)


def semesters(today):
    result = []
    for year in range(max(2026, today.year - 1), max(2026, today.year) + 2):
        for number in (1, 2):
            key = (year, number)
            start = VERIFIED_STARTS.get(key)
            if start is None:
                start = first_monday(year if number == 1 else year + 1,
                                     8 if number == 1 else 1) + timedelta(days=7)
            result.append((year, number, start, key not in VERIFIED_STARTS))
    return sorted(result, key=lambda semester: semester[2])


def status(today):
    terms = semesters(today)
    for year, number, start, estimated in terms:
        day = (today - start).days
        # Include orientation as Week 0 for Semester 1 only.
        if not (-7 <= day <= 117 if number == 1 else 0 <= day <= 117):
            continue
        if day < 0:
            label, phase, begin, end = "W0", "Orientation", start - timedelta(days=7), start - timedelta(days=1)
        elif day < 40:
            week = day // 7 + 1
            begin = start + timedelta(weeks=week - 1)
            end = min(begin + timedelta(days=6), start + timedelta(days=39))
            label, phase = f"W{week}", f"Instructional Week {week}"
        elif day < 49:
            label, phase = "Recess", "Recess"
            begin, end = start + timedelta(days=40), start + timedelta(days=48)
        elif day < 96:
            week = (day - 49) // 7 + 7
            begin = start + timedelta(days=49, weeks=week - 7)
            end = min(begin + timedelta(days=6), start + timedelta(days=95))
            label, phase = f"W{week}", f"Instructional Week {week}"
        elif day < 103:
            label, phase = "Read", "Reading Week"
            begin, end = start + timedelta(days=96), start + timedelta(days=102)
        else:
            label, phase = "Exam", "Examinations"
            begin, end = start + timedelta(days=103), start + timedelta(days=117)
        tooltip = (f"NUS AY{year}/{year + 1} · Semester {number}\n"
                   f"{phase}: {begin:%d %b %Y} – {end:%d %b %Y}\n"
                   "Teaching weeks continue through weekends until the next phase.")
        if day < 0:
            tooltip += f"\nTeaching starts {start:%a, %d %b %Y}."
        if estimated:
            tooltip += "\nEstimated: repeats AY2026/27 week pattern."
        else:
            tooltip += "\nOfficial NUS AY2026/27 calendar."
        tooltip += f"\n{SOURCE}"
        return {"text": label, "tooltip": tooltip,
                "class": "estimated" if estimated else "semester"}

    year, number, start, estimated = next(term for term in terms if term[2] > today)
    days = (start - today).days
    weeks = (days + 6) // 7
    tooltip = (f"NUS vacation · {days} day{'s' if days != 1 else ''} until teaching starts\n"
               f"AY{year}/{year + 1} Semester {number}: {start:%a, %d %b %Y}\n"
               "Week countdown rounds up; special terms are treated as vacation.")
    if estimated:
        tooltip += "\nEstimated: repeats AY2026/27 week pattern."
    else:
        tooltip += "\nOfficial NUS AY2026/27 calendar."
    tooltip += f"\n{SOURCE}"
    return {"text": f"{weeks}w", "tooltip": tooltip,
            "class": ["vacation", "estimated"] if estimated else "vacation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="Preview an ISO date (YYYY-MM-DD)")
    args = parser.parse_args()
    today = args.date or datetime.now(ZoneInfo("Asia/Singapore")).date()
    print(json.dumps(status(today), ensure_ascii=False))


if __name__ == "__main__":
    main()
