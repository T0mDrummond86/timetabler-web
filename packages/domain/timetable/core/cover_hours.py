"""Hours attached to a logged cover job, and the under-hours ledger.

A lecturer under their contracted hours owes time over the semester, and
covering someone else's class is how that time is paid back. This module holds
the two pieces of arithmetic: how long a cover job was, and how much a lecturer
still owes once their cover is counted.
"""
from __future__ import annotations

import re

# Semester length used to turn a weekly variance into a total for the term.
# Deliberately a constant rather than Semester.num_weeks (which defaults to 18)
# so the figure matches the one the business actually uses.
SEMESTER_WEEKS_FOR_OWED_HOURS = 20

SLOT_MINUTES = 30

# "09:00 – 12:00", "9:00-12:00", "09.00 — 12.00" and friends.
_TIME_LABEL = re.compile(
    r"(\d{1,2})\s*[:.]\s*(\d{2})\s*[-–—to]+\s*(\d{1,2})\s*[:.]\s*(\d{2})",
    re.IGNORECASE,
)


def hours_from_slots(start_slot: int | None, end_slot: int | None) -> float | None:
    """Exact length of a booking, from the slot grid."""
    if start_slot is None or end_slot is None:
        return None
    span = int(end_slot) - int(start_slot)
    if span <= 0:
        return None
    return round(span * SLOT_MINUTES / 60, 2)


def hours_from_time_label(label: str | None) -> float | None:
    """Best-effort length from a display label, for rows logged before hours
    were recorded. Returns None when the label cannot be read, which callers
    must treat as zero rather than as an error."""
    if not label:
        return None
    m = _TIME_LABEL.search(str(label))
    if not m:
        return None
    sh, sm, eh, em = (int(g) for g in m.groups())
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 24 and 0 <= em <= 59):
        return None
    minutes = (eh * 60 + em) - (sh * 60 + sm)
    if minutes <= 0:
        return None
    return round(minutes / 60, 2)


def hours_owed_for_variance(variance: float | None) -> float | None:
    """Total hours a lecturer owes for the semester.

    Only under-hours lecturers are tracked: a variance at or above zero returns
    None, so the ledger columns stay empty for anyone on or over target.
    """
    if variance is None or variance >= 0:
        return None
    return round(abs(variance) * SEMESTER_WEEKS_FOR_OWED_HOURS, 2)


def still_to_make_up(owed: float | None, covered: float) -> float | None:
    """What is left after cover is credited. Never negative — covering more
    than you owe means you are square, not in credit."""
    if owed is None:
        return None
    return round(max(0.0, owed - (covered or 0.0)), 2)
