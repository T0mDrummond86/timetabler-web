"""Parse an NMT-style academic calendar CSV into teaching weeks.

The calendar is a human-formatted spreadsheet: three header rows of four
months each, every month a mini-table of seven weekday rows then a
week-number row. Rows are ragged (leading blanks differ per weekday), so we
avoid fixed-column parsing: dates are grouped by ISO week, and each month's
week-number tokens are paired with the ordered ISO weeks of that month.

Output: a list of CalendarWeekRow(semester, week_number, monday_date, label)
for teaching weeks, plus non-teaching weeks (label set, week_number 0).
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import re
from dataclasses import dataclass

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_MONTH_RE = re.compile(r"\s*(" + "|".join(_MONTHS) + r")\s+(\d{4})")
_DAY_LABELS = ["M", "TU", "W", "TH", "F", "S", "S"]


@dataclass
class CalendarWeekRow:
    semester: int
    week_number: int
    monday_date: _dt.date
    label: str


def _header_rows(rows: list[list[str]]) -> list[tuple[int, list[tuple[int, int, int]]]]:
    out: list[tuple[int, list[tuple[int, int, int]]]] = []
    for r, row in enumerate(rows):
        cols: list[tuple[int, int, int]] = []
        for c, val in enumerate(row):
            m = _MONTH_RE.match(val.strip())
            if m:
                cols.append((c, _MONTHS[m.group(1)], int(m.group(2))))
        if cols:
            out.append((r, cols))
    return out


def _month_mondays_and_tokens(
    rows: list[list[str]],
    hrow: int,
    cols: list[tuple[int, int, int]],
    mi: int,
) -> tuple[list[_dt.date], list[str]]:
    """Return ordered Monday dates and week-number tokens for one month block."""
    ccol, month, year = cols[mi]
    pos = [c for c, _, _ in cols] + [10**9]
    day_rows = rows[hrow + 1 : hrow + 8]
    weeknum_row = rows[hrow + 8] if hrow + 8 < len(rows) else []

    days: set[int] = set()
    for di, drow in enumerate(day_rows):
        label = _DAY_LABELS[di]
        segments: list[list[str]] = []
        cur: list[str] | None = None
        for tok in drow:
            t = tok.strip()
            if t == label:
                cur = []
                segments.append(cur)
            elif cur is not None:
                cur.append(t)
        if mi < len(segments):
            for t in segments[mi]:
                if t.isdigit():
                    days.add(int(t))
                elif t:
                    break

    mondays: dict[_dt.date, bool] = {}
    for d in days:
        try:
            date = _dt.date(year, month, d)
        except ValueError:
            continue
        monday = date - _dt.timedelta(days=date.weekday())
        mondays[monday] = True
    ordered = sorted(mondays)

    col_lo, col_hi = pos[mi], pos[mi + 1]
    toks = [
        weeknum_row[c].strip() if c < len(weeknum_row) else ""
        for c in range(col_lo, col_hi)
    ]
    # Position 0 of the slice is the day-label column; week columns follow.
    vals = toks[1 : 1 + len(ordered)]
    return ordered, vals


def parse_calendar_csv(content: bytes | str) -> list[CalendarWeekRow]:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    rows = list(csv.reader(io.StringIO(text)))

    label_by_monday: dict[_dt.date, str] = {}
    for hrow, cols in _header_rows(rows):
        for mi in range(len(cols)):
            mondays, vals = _month_mondays_and_tokens(rows, hrow, cols, mi)
            for monday, label in zip(mondays, vals):
                # Boundary weeks appear in two months: keep the non-empty label.
                if monday in label_by_monday and label == "":
                    continue
                label_by_monday[monday] = label

    # Assign semesters: a teaching-week numbered 1 starts a new semester.
    out: list[CalendarWeekRow] = []
    current_sem = 1
    seen_first = False
    for monday in sorted(label_by_monday):
        label = label_by_monday[monday]
        num_match = re.match(r"(\d+)", label)
        if num_match:
            week_number = int(num_match.group(1))
            if week_number == 1:
                if seen_first:
                    current_sem = 2
                seen_first = True
            # Preserve any suffix (e.g. "21 NC") as the label.
            suffix = label[num_match.end():].strip()
            out.append(
                CalendarWeekRow(current_sem, week_number, monday, suffix)
            )
        else:
            out.append(CalendarWeekRow(current_sem, 0, monday, label))

    return out
