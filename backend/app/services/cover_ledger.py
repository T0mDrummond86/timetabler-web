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


def session_ledger_by_lecturer(db: Session, timetable_session_id: int) -> dict[str, dict]:
    """The cover ledger for every lecturer, as seen from one member session.

    Keyed by normalised name, so a caller holding session-local staff rows can
    look each one up.

    The variance used is the workspace-**aggregated** one, not the session's own.
    A lecturer teaching across two linked timetables is short against their
    combined load, not against either half, and the cover panel and cover log
    already report it that way. Using the local figure here would show the same
    person owing two different amounts on two screens.

    Returns an empty mapping when the session belongs to no workspace; there is
    no cover log to read in that case, and the caller decides what to fall back
    to.
    """
    from .global_sessions import aggregated_staff, global_session_for_timetable

    gs = global_session_for_timetable(db, timetable_session_id)
    if gs is None:
        return {}

    covered = cover_hours_by_lecturer(db, gs.id)
    out: dict[str, dict] = {}
    for row in aggregated_staff(db, gs.id):
        key = normalize_staff_name(row.get("name"))
        if not key:
            continue
        out[key] = ledger_for(row.get("variance"), covered.get(key, 0.0))
    return out
