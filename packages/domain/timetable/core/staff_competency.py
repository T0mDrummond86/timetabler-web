"""Lecturer eligibility per class (Classes tab lecturer checkboxes)."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from .models import Staff, StaffCompetency


def constrained_staff_ids_for_unit(session: Session, unit_id: int) -> set[int]:
    """Staff explicitly ticked on the Classes tab for this unit (may be empty)."""
    return {
        sid
        for (sid,) in session.query(StaffCompetency.staff_id)
        .filter(StaffCompetency.unit_id == unit_id)
        .all()
    }


def eligible_staff_ids_for_unit(
    session: Session,
    unit_id: int | None,
    *,
    staff_ids: Iterable[int] | None = None,
) -> list[int]:
    """Staff who may be assigned to teach ``unit_id``.

    Classes tab rule (same as the booking dialog and CP-SAT solver):
    - No lecturer checkboxes ticked for the class → any lecturer may teach it.
    - One or more ticked → only those lecturers.
    """
    if staff_ids is None:
        all_ids = [s.id for s in session.query(Staff).order_by(Staff.name).all()]
    else:
        all_ids = list(staff_ids)
    if unit_id is None:
        return all_ids
    constrained = constrained_staff_ids_for_unit(session, unit_id)
    if not constrained:
        return all_ids
    return [sid for sid in all_ids if sid in constrained]


def unit_has_unsatisfiable_lecturer_constraint(
    session: Session,
    unit_id: int,
    *,
    staff_ids: Iterable[int] | None = None,
) -> bool:
    """True when ticked lecturers exist but none are valid staff rows (data error)."""
    if staff_ids is None:
        all_ids = {s.id for s in session.query(Staff).all()}
    else:
        all_ids = set(staff_ids)
    constrained = constrained_staff_ids_for_unit(session, unit_id)
    if not constrained:
        return False
    return not (constrained & all_ids)
