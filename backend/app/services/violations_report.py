"""Flatten validation violations into report rows (desktop violations tab)."""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from timetable.constants import DAYS, NUM_SLOTS, slot_to_time
from timetable.core.models import Booking, Week
from timetable.core.clash_check_settings import filter_violations_by_clash_settings, load_clash_check_settings
from timetable.core.tenancy_models import TimetableSession
from timetable.core.validation import Severity

from .timetable_grid import get_repeating_week
from .violation_cache import get_week_violations

HEADERS = (
    "severity",
    "type",
    "ID",
    "group",
    "class",
    "lecturer",
    "day",
    "time",
    "room",
    "description",
)


def _slot_range_str(start_slot: int, end_slot: int) -> str:
    end_s = "22:00" if end_slot >= NUM_SLOTS else slot_to_time(end_slot).strftime("%H:%M")
    return f"{slot_to_time(start_slot).strftime('%H:%M')}–{end_s}"


def _booking_fields(b: Booking | None) -> dict[str, str]:
    if b is None:
        return {
            "group": "",
            "class": "",
            "lecturer": "",
            "day": "",
            "time": "",
            "room": "",
            "id": "",
        }
    return {
        "group": b.course.code if b.course else "",
        "class": b.unit.name if b.unit else "",
        "lecturer": b.staff.name if b.staff else "",
        "day": DAYS[b.day] if 0 <= b.day < len(DAYS) else str(b.day),
        "time": _slot_range_str(b.start_slot, b.end_slot),
        "room": b.room.code if b.room else "",
        "id": (b.external_id or "").strip(),
    }


def _merge(values: list[str], *, sep: str = " · ") -> str:
    seen: list[str] = []
    for v in values:
        v = (v or "").strip()
        if v and v not in seen:
            seen.append(v)
    return sep.join(seen)


def violations_report(
    db: Session,
    *,
    timetable_session_id: int,
    severity: str | None = None,
) -> dict:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return {"summary": "No repeating week", "rows": [], "headers": list(HEADERS)}

    violations = get_week_violations(db, week.id)
    session_row = db.get(TimetableSession, timetable_session_id)
    if session_row is not None:
        violations = filter_violations_by_clash_settings(
            violations, load_clash_check_settings(session_row)
        )
    if severity == "hard":
        violations = [v for v in violations if v.severity == Severity.HARD]
    elif severity == "soft":
        violations = [v for v in violations if v.severity == Severity.SOFT]

    booking_ids = {bid for v in violations for bid in v.booking_ids}
    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.course),
            joinedload(Booking.unit),
            joinedload(Booking.staff),
            joinedload(Booking.room),
        )
        .filter(Booking.id.in_(booking_ids or [-1]))
        .all()
    )
    by_id = {b.id: b for b in bookings}

    rows: list[dict] = []
    for v in violations:
        fields = [_booking_fields(by_id.get(bid)) for bid in v.booking_ids]
        rows.append(
            {
                "severity": v.severity.value,
                "type": v.code,
                "ID": _merge([f["id"] for f in fields]),
                "group": _merge([f["group"] for f in fields]),
                "class": _merge([f["class"] for f in fields]),
                "lecturer": _merge([f["lecturer"] for f in fields]),
                "day": _merge([f["day"] for f in fields]),
                "time": _merge([f["time"] for f in fields]),
                "room": _merge([f["room"] for f in fields]),
                "description": v.message,
                "booking_ids": list(v.booking_ids),
            }
        )

    hard_n = sum(1 for v in violations if v.severity == Severity.HARD)
    soft_n = sum(1 for v in violations if v.severity == Severity.SOFT)
    summary = f"{len(rows)} warning(s) — {hard_n} hard, {soft_n} soft"

    return {"summary": summary, "rows": rows, "headers": list(HEADERS)}
