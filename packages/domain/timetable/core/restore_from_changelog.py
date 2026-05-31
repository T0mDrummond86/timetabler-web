"""Restore booking rows from a change-log entry's stored before/after snapshots."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import Booking, ChangeLogEntry


def restore_bookings_from_changelog(
    session: Session,
    entry_id: int,
    *,
    use_before: bool = True,
) -> int:
    """Re-apply booking field snapshots from ``change_log.details``.

    Returns the number of bookings updated. Raises if the entry is missing or
    has no booking payloads.
    """
    row = session.get(ChangeLogEntry, entry_id)
    if row is None or not row.details:
        raise ValueError(f"Change log entry {entry_id} not found or has no details")
    payload = json.loads(row.details)
    bookings = payload.get("bookings")
    if not isinstance(bookings, dict):
        raise ValueError(f"Change log entry {entry_id} has no booking snapshots")

    key = "before" if use_before else "after"
    n = 0
    for bid_str, snap in bookings.items():
        if not isinstance(snap, dict):
            continue
        state = snap.get(key)
        if state is None:
            continue
        bid = int(bid_str)
        b = session.get(Booking, bid)
        if b is None:
            continue
        for field, value in state.items():
            setattr(b, field, value)
        n += 1
    session.commit()
    return n
