"""Per-class lecturer delivery counts and custodian (primary owner) selection.

The **custodian** for a class is the staff member with the most bookings for that
:class:`Unit` where :attr:`Booking.staff_id` is set. Ties break alphabetically by
name, then by staff id.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Booking, Staff, Unit


@dataclass(frozen=True)
class LecturerDelivery:
    staff_id: int
    name: str
    deliveries: int


@dataclass(frozen=True)
class ClassCustodianRow:
    unit_id: int
    unit_name: str
    """Bookings for this unit with a lecturer assigned, grouped and sorted."""
    lecturer_deliveries: tuple[LecturerDelivery, ...]
    """Bookings for this unit with no ``staff_id`` (still on the timetable)."""
    unassigned_deliveries: int
    custodian: LecturerDelivery | None


def _sorted_lecturer_rows(
    counts_by_staff: dict[int, int], staff_name: dict[int, str]
) -> tuple[LecturerDelivery, ...]:
    items: list[LecturerDelivery] = [
        LecturerDelivery(sid, staff_name.get(sid, f"#{sid}"), counts_by_staff[sid])
        for sid in counts_by_staff
    ]
    items.sort(key=lambda r: (-r.deliveries, (r.name or "").lower(), r.staff_id))
    return tuple(items)


def class_custodian_rows(session: Session) -> list[ClassCustodianRow]:
    """One row per :class:`Unit`, ordered by class name.

    Counts every booking with a non-null ``unit_id`` across all weeks in the
    session. Only rows with a non-null ``staff_id`` contribute to lecturer totals
    and custodian selection; unassigned bookings are reported separately.
    """
    units = session.query(Unit).order_by(Unit.name).all()
    assigned = (
        session.query(Booking.unit_id, Booking.staff_id, func.count(Booking.id))
        .filter(Booking.unit_id.isnot(None), Booking.staff_id.isnot(None))
        .group_by(Booking.unit_id, Booking.staff_id)
        .all()
    )
    unassigned = (
        session.query(Booking.unit_id, func.count(Booking.id))
        .filter(Booking.unit_id.isnot(None), Booking.staff_id.is_(None))
        .group_by(Booking.unit_id)
        .all()
    )

    by_unit_staff: dict[int, dict[int, int]] = {}
    for uid, sid, n in assigned:
        by_unit_staff.setdefault(uid, {})[sid] = int(n)

    unassigned_by_unit: dict[int, int] = {int(uid): int(n) for uid, n in unassigned}

    staff_ids: set[int] = set()
    for m in by_unit_staff.values():
        staff_ids.update(m.keys())
    staff_name: dict[int, str] = {}
    if staff_ids:
        for s in session.query(Staff).filter(Staff.id.in_(staff_ids)).all():
            staff_name[s.id] = s.name or f"#{s.id}"

    out: list[ClassCustodianRow] = []
    for u in units:
        counts = by_unit_staff.get(u.id, {})
        lecturers = _sorted_lecturer_rows(counts, staff_name)
        custodian = lecturers[0] if lecturers else None
        out.append(
            ClassCustodianRow(
                unit_id=u.id,
                unit_name=u.name or "(unnamed)",
                lecturer_deliveries=lecturers,
                unassigned_deliveries=unassigned_by_unit.get(u.id, 0),
                custodian=custodian,
            )
        )
    return out


def format_lecturer_deliveries_cell(row: ClassCustodianRow) -> str:
    """Single-line summary for the lecturers column."""
    parts: list[str] = [f"{d.name} ({d.deliveries})" for d in row.lecturer_deliveries]
    if row.unassigned_deliveries:
        parts.append(f"Unassigned ({row.unassigned_deliveries})")
    return ", ".join(parts) if parts else "—"
