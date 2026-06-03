"""Session-scoped violation dismissals (web persistence for desktop parity)."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import ViolationDismissal
from timetable.core.validation import Violation


def dismissed_keys(db: Session, *, timetable_session_id: int) -> set[tuple[int, str]]:
    rows = (
        db.query(ViolationDismissal.booking_id, ViolationDismissal.code)
        .filter(ViolationDismissal.timetable_session_id == timetable_session_id)
        .all()
    )
    return {(int(bid), str(code)) for bid, code in rows}


def dismiss_violation(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    code: str,
) -> None:
    code = code.strip()
    if not code:
        raise ValueError("Violation code is required")
    existing = (
        db.query(ViolationDismissal)
        .filter(
            ViolationDismissal.timetable_session_id == timetable_session_id,
            ViolationDismissal.booking_id == booking_id,
            ViolationDismissal.code == code,
        )
        .first()
    )
    if existing is None:
        db.add(
            ViolationDismissal(
                timetable_session_id=timetable_session_id,
                booking_id=booking_id,
                code=code,
            )
        )
        db.flush()


def clear_booking_dismissals(
    db: Session,
    *,
    timetable_session_id: int,
    booking_ids: Iterable[int],
) -> None:
    ids = {int(i) for i in booking_ids if i is not None}
    if not ids:
        return
    (
        db.query(ViolationDismissal)
        .filter(
            ViolationDismissal.timetable_session_id == timetable_session_id,
            ViolationDismissal.booking_id.in_(ids),
        )
        .delete(synchronize_session=False)
    )
    db.flush()


def clear_all_dismissals(db: Session, *, timetable_session_id: int) -> None:
    (
        db.query(ViolationDismissal)
        .filter(ViolationDismissal.timetable_session_id == timetable_session_id)
        .delete()
    )
    db.flush()


def filter_violations(
    dismissed: set[tuple[int, str]],
    booking_id: int,
    violations: list[Violation],
) -> list[Violation]:
    if not dismissed:
        return list(violations)
    return [v for v in violations if (booking_id, v.code) not in dismissed]


def apply_dismissals_to_map(
    dismissed: set[tuple[int, str]],
    by_booking: dict[int, list[Violation]],
) -> dict[int, list[Violation]]:
    return {
        bid: filter_violations(dismissed, bid, vlist)
        for bid, vlist in by_booking.items()
    }
