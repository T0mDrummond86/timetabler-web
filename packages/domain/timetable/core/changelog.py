"""Audit log: append rows and resolve net booking deltas from timetabling edits."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .booking_snapshots import describe_booking_changes, summarise_booking_change
from .models import ChangeLogEntry

TIMETABLING_LOG_ACTIONS = frozenset({"change", "undo", "redo"})


def log(session: Session, action: str, description: str, details: dict | None = None) -> None:
    """Append a row to change_log. Caller is responsible for committing the session."""
    entry = ChangeLogEntry(
        action=action,
        description=description,
        details=json.dumps(details) if details else None,
    )
    session.add(entry)
    session.commit()


def booking_change_log_payload(
    session: Session,
    before: dict[int, dict | None],
    after: dict[int, dict | None],
    *,
    header: str,
) -> tuple[str, dict]:
    """Build change-log description and JSON details for a booking mutation."""
    diff_lines = describe_booking_changes(session, before, after)
    summary = summarise_booking_change(before, after, diff_lines)
    description = f"{header} — {summary}" if summary else header
    bookings_payload = {
        str(bid): {"before": before.get(bid), "after": after.get(bid)}
        for bid in set(before) | set(after)
    }
    return description, {"diff": diff_lines, "bookings": bookings_payload}


def resolve_session_booking_net_maps(
    session: Session,
    *,
    timetable_session_id: int | None = None,
) -> tuple[dict[int, dict | None], dict[int, dict | None]]:
    """First / last booking snapshots per id from timetabling change-log entries."""
    first_before: dict[int, dict | None] = {}
    last_after: dict[int, dict | None] = {}
    seen: set[int] = set()
    q = session.query(ChangeLogEntry).order_by(ChangeLogEntry.id)
    if timetable_session_id is not None:
        q = q.filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
    rows = q.all()
    for row in rows:
        if row.action not in TIMETABLING_LOG_ACTIONS or not row.details:
            continue
        try:
            payload = json.loads(row.details)
        except Exception:
            continue
        bookings = payload.get("bookings") if isinstance(payload, dict) else None
        if not isinstance(bookings, dict):
            continue
        for bid_str, snap in bookings.items():
            try:
                bid = int(bid_str)
            except ValueError:
                continue
            before = snap.get("before") if isinstance(snap, dict) else None
            after = snap.get("after") if isinstance(snap, dict) else None
            if bid not in seen:
                first_before[bid] = before
                seen.add(bid)
            last_after[bid] = after

    before_map: dict[int, dict | None] = {}
    after_map: dict[int, dict | None] = {}
    for bid in seen:
        b0 = first_before.get(bid)
        b1 = last_after.get(bid)
        if b0 == b1:
            continue
        before_map[bid] = b0
        after_map[bid] = b1
    return before_map, after_map


def resolve_session_log(session: Session) -> list[str]:
    """Net booking deltas as prose lines."""
    before_map, after_map = resolve_session_booking_net_maps(session)
    if not before_map and not after_map:
        return []
    return describe_booking_changes(session, before_map, after_map)
