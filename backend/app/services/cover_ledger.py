"""Cover hours accrued per lecturer, and what an under-hours lecturer still owes.

Cover jobs are logged against a global workspace, so the ledger is workspace
wide: a lecturer who covers a class in one timetable has that time counted
whichever session the shortfall arose in.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.cover_hours import hours_owed_for_variance, still_to_make_up
from timetable.core.tenancy_models import CoverLogEntry


def normalize_staff_name(name: str | None) -> str:
    """Match the key ``aggregated_staff`` amalgamates lecturers by."""
    return (name or "").strip().casefold()


def cover_hours_by_lecturer(db: Session, global_session_id: int) -> dict[str, float]:
    """Total logged cover hours per lecturer, keyed by normalised name.

    Only the covering lecturer is credited — being covered is not a debit.
    Rows whose hours could not be determined count as zero rather than
    invalidating the total.
    """
    totals: dict[str, float] = {}
    rows = (
        db.query(CoverLogEntry.cover_staff_name, CoverLogEntry.hours)
        .filter(CoverLogEntry.global_session_id == global_session_id)
        .all()
    )
    for name, hours in rows:
        key = normalize_staff_name(name)
        if not key:
            continue
        totals[key] = round(totals.get(key, 0.0) + float(hours or 0.0), 2)
    return totals


def ledger_for(variance, covered: float) -> dict:
    """The three ledger figures for one lecturer.

    ``variance`` comes from the amalgamated staff row, which yields the string
    ``"Varies"`` when a lecturer's sessions disagree; there is no single
    shortfall to report in that case, so the figures stay empty.
    """
    numeric = variance if isinstance(variance, (int, float)) else None
    owed = hours_owed_for_variance(numeric)
    if owed is None:
        # On or over target, or no single variance: nothing to make up.
        return {"hours_owed": None, "cover_hours_done": None, "still_to_make_up": None}
    return {
        "hours_owed": owed,
        # Shown as 0 rather than blank so the column reads as a ledger.
        "cover_hours_done": round(covered or 0.0, 2),
        "still_to_make_up": still_to_make_up(owed, covered),
    }
