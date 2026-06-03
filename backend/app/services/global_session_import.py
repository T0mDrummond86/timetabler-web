"""Copy staff and qualifications from a linked session in the same global group."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from timetable.core.models import (
    Qualification,
    Staff,
    StaffAvailability,
    StaffPreference,
    Unit,
    UnitQualification,
)
from timetable.core.qualification_schedule import replace_qualification_time_windows
from timetable.core.sidebar_order import next_staff_sidebar_order

from .entity_crud import set_unit_qualifications
from .global_sessions import global_session_for_timetable, normalize_staff_name
from .global_staff_hours import (
    copy_staff_online_overrides,
    propagate_staff_hours_profile,
    propagate_staff_online_overrides,
)
from .qualification_editor import sync_qualification_regular_groups
from .timetable_grid import assert_session_in_org


def linked_sessions_for_timetable(
    db: Session, *, timetable_session_id: int, organization_id: int
) -> list[dict]:
    """Other timetable sessions in the same global group."""
    assert_session_in_org(db, timetable_session_id, organization_id)
    gs = global_session_for_timetable(db, timetable_session_id)
    if gs is None:
        return []
    from timetable.core.tenancy_models import GlobalSessionMember, TimetableSession

    rows = (
        db.query(TimetableSession)
        .join(
            GlobalSessionMember,
            GlobalSessionMember.timetable_session_id == TimetableSession.id,
        )
        .filter(
            GlobalSessionMember.global_session_id == gs.id,
            TimetableSession.id != timetable_session_id,
        )
        .order_by(TimetableSession.name)
        .all()
    )
    return [{"id": r.id, "name": r.name} for r in rows]


def _assert_import_pair(
    db: Session,
    *,
    target_session_id: int,
    source_session_id: int,
    organization_id: int,
) -> None:
    if target_session_id == source_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target session must be different",
        )
    assert_session_in_org(db, target_session_id, organization_id)
    assert_session_in_org(db, source_session_id, organization_id)
    tgt_gs = global_session_for_timetable(db, target_session_id)
    src_gs = global_session_for_timetable(db, source_session_id)
    if tgt_gs is None or src_gs is None or tgt_gs.id != src_gs.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both sessions must belong to the same global group",
        )


def _existing_staff_names(db: Session, session_id: int) -> set[str]:
    return {
        normalize_staff_name(s.name)
        for s in db.query(Staff).filter(Staff.timetable_session_id == session_id).all()
    }


def _existing_qual_names(db: Session, session_id: int) -> set[str]:
    return {
        (q.name or "").strip().casefold()
        for q in db.query(Qualification).filter(Qualification.timetable_session_id == session_id).all()
    }


def _existing_unit_names(db: Session, session_id: int) -> set[str]:
    return {
        (u.name or "").strip().casefold()
        for u in db.query(Unit).filter(Unit.timetable_session_id == session_id).all()
    }


def _units_for_qualification(db: Session, qualification_id: int) -> list[Unit]:
    return (
        db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qualification_id)
        .order_by(Unit.name)
        .all()
    )


def import_options(
    db: Session,
    *,
    target_session_id: int,
    source_session_id: int,
    organization_id: int,
) -> dict:
    """Rows the user can pick in the import dialog."""
    _assert_import_pair(
        db,
        target_session_id=target_session_id,
        source_session_id=source_session_id,
        organization_id=organization_id,
    )
    existing_staff = _existing_staff_names(db, target_session_id)
    existing_qual = _existing_qual_names(db, target_session_id)

    staff_options: list[dict] = []
    for s in (
        db.query(Staff)
        .filter(Staff.timetable_session_id == source_session_id)
        .order_by(Staff.name)
        .all()
    ):
        staff_options.append(
            {
                "id": s.id,
                "name": s.name,
                "already_in_target": normalize_staff_name(s.name) in existing_staff,
            }
        )

    qual_options: list[dict] = []
    for q in (
        db.query(Qualification)
        .filter(Qualification.timetable_session_id == source_session_id)
        .order_by(Qualification.name)
        .all()
    ):
        linked = _units_for_qualification(db, q.id)
        qual_options.append(
            {
                "id": q.id,
                "name": q.name,
                "linked_classes": [u.name for u in linked],
                "already_in_target": (q.name or "").strip().casefold() in existing_qual,
            }
        )

    return {"staff": staff_options, "qualifications": qual_options}


def _copy_unit_to_target(
    db: Session,
    *,
    src_unit: Unit,
    target_session_id: int,
    existing_unit_names: set[str],
) -> Unit:
    key = (src_unit.name or "").strip().casefold()
    if not key:
        raise ValueError("empty class name")
    existing = (
        db.query(Unit)
        .filter(Unit.timetable_session_id == target_session_id)
        .all()
    )
    for u in existing:
        if (u.name or "").strip().casefold() == key:
            return u
    row = Unit(
        name=src_unit.name.strip(),
        timetable_session_id=target_session_id,
        length_slots=src_unit.length_slots,
        component_codes=src_unit.component_codes,
        required_room_type=src_unit.required_room_type,
        required_capacity=src_unit.required_capacity,
        double_session=getattr(src_unit, "double_session", 0) or 0,
        double_session_same_day=getattr(src_unit, "double_session_same_day", None),
        double_session_first_slots=getattr(src_unit, "double_session_first_slots", None),
    )
    db.add(row)
    db.flush()
    existing_unit_names.add(key)
    return row


def import_staff_from_linked_session(
    db: Session,
    *,
    target_session_id: int,
    source_session_id: int,
    organization_id: int,
    staff_ids: list[int],
) -> dict:
    _assert_import_pair(
        db,
        target_session_id=target_session_id,
        source_session_id=source_session_id,
        organization_id=organization_id,
    )
    if not staff_ids:
        return {"added": [], "skipped": []}

    existing = _existing_staff_names(db, target_session_id)
    source_rows = (
        db.query(Staff)
        .options(
            joinedload(Staff.availability),
            joinedload(Staff.preferences),
        )
        .filter(
            Staff.timetable_session_id == source_session_id,
            Staff.id.in_(staff_ids),
        )
        .all()
    )
    by_id = {s.id: s for s in source_rows}
    added: list[str] = []
    skipped: list[dict] = []
    for sid in staff_ids:
        src = by_id.get(sid)
        if src is None:
            skipped.append({"name": f"#{sid}", "reason": "not found in source session"})
            continue
        key = normalize_staff_name(src.name)
        if not key:
            skipped.append({"name": src.name, "reason": "empty name"})
            continue
        if key in existing:
            skipped.append({"name": src.name, "reason": "already in target session"})
            continue
        row = Staff(
            name=src.name.strip(),
            timetable_session_id=target_session_id,
            max_hours_per_week=src.max_hours_per_week,
            non_teaching_day=src.non_teaching_day,
            fte=src.fte,
            ot_hours=src.ot_hours,
            development_project_hours=src.development_project_hours,
            development_project_description=src.development_project_description,
            tae_hours=src.tae_hours,
            supervision_hours=src.supervision_hours,
            default_online_students_per_class=src.default_online_students_per_class,
            timetable_locked=getattr(src, "timetable_locked", 0) or 0,
            sidebar_order=next_staff_sidebar_order(db),
        )
        db.add(row)
        db.flush()
        for av in src.availability:
            db.add(
                StaffAvailability(
                    staff_id=row.id,
                    day=av.day,
                    start_slot=av.start_slot,
                    end_slot=av.end_slot,
                )
            )
        for pref in src.preferences:
            db.add(
                StaffPreference(
                    staff_id=row.id,
                    priority=pref.priority,
                    slot_number=pref.slot_number,
                    qualification_name=pref.qualification_name,
                    class_name=pref.class_name,
                    unit_id=None,
                )
            )
        copy_staff_online_overrides(
            db,
            source_staff_id=src.id,
            source_session_id=source_session_id,
            target_staff_id=row.id,
            target_session_id=target_session_id,
        )
        db.flush()
        propagate_staff_hours_profile(db, src)
        propagate_staff_online_overrides(db, src)
        existing.add(key)
        added.append(row.name)
    db.flush()
    return {"added": added, "skipped": skipped}


def import_qualifications_from_linked_session(
    db: Session,
    *,
    target_session_id: int,
    source_session_id: int,
    organization_id: int,
    qualification_ids: list[int],
) -> dict:
    _assert_import_pair(
        db,
        target_session_id=target_session_id,
        source_session_id=source_session_id,
        organization_id=organization_id,
    )
    if not qualification_ids:
        return {"added": [], "classes_added": [], "skipped": []}

    existing_qual = _existing_qual_names(db, target_session_id)
    existing_units = _existing_unit_names(db, target_session_id)
    source_rows = (
        db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == source_session_id,
            Qualification.id.in_(qualification_ids),
        )
        .all()
    )
    by_id = {q.id: q for q in source_rows}
    added: list[str] = []
    classes_added: list[str] = []
    skipped: list[dict] = []

    for qid in qualification_ids:
        src = by_id.get(qid)
        if src is None:
            skipped.append({"name": f"#{qid}", "reason": "not found in source session"})
            continue
        key = (src.name or "").strip().casefold()
        if not key:
            skipped.append({"name": src.name, "reason": "empty name"})
            continue
        if key in existing_qual:
            skipped.append({"name": src.name, "reason": "already in target session"})
            continue

        row = Qualification(
            name=src.name.strip(),
            timetable_session_id=target_session_id,
            num_groups=1,
            schedule_period=getattr(src, "schedule_period", None) or "day",
            delivery_mode=getattr(src, "delivery_mode", None) or "regular",
            block_week_count=getattr(src, "block_week_count", None),
            block_start_semester_week=getattr(src, "block_start_semester_week", None),
        )
        db.add(row)
        db.flush()
        replace_qualification_time_windows(db, row)
        if (getattr(row, "delivery_mode", None) or "regular") == "regular":
            sync_qualification_regular_groups(db, row, 1)

        for src_unit in _units_for_qualification(db, src.id):
            unit_key = (src_unit.name or "").strip().casefold()
            if not unit_key:
                continue
            was_new = unit_key not in existing_units
            tgt_unit = _copy_unit_to_target(
                db,
                src_unit=src_unit,
                target_session_id=target_session_id,
                existing_unit_names=existing_units,
            )
            current_links = [
                int(r[0])
                for r in db.query(UnitQualification.qualification_id)
                .filter(UnitQualification.unit_id == tgt_unit.id)
                .all()
            ]
            if row.id not in current_links:
                current_links.append(row.id)
                set_unit_qualifications(
                    db,
                    timetable_session_id=target_session_id,
                    unit_id=tgt_unit.id,
                    qualification_ids=current_links,
                )
            if was_new and tgt_unit.name not in classes_added:
                classes_added.append(tgt_unit.name)

        existing_qual.add(key)
        added.append(row.name)

    db.flush()
    return {"added": added, "classes_added": classes_added, "skipped": skipped}


def import_from_linked_session(
    db: Session,
    *,
    target_session_id: int,
    source_session_id: int,
    organization_id: int,
    staff_ids: list[int] | None = None,
    qualification_ids: list[int] | None = None,
) -> dict:
    out: dict = {}
    if staff_ids:
        out["staff"] = import_staff_from_linked_session(
            db,
            target_session_id=target_session_id,
            source_session_id=source_session_id,
            organization_id=organization_id,
            staff_ids=staff_ids,
        )
    if qualification_ids:
        out["qualifications"] = import_qualifications_from_linked_session(
            db,
            target_session_id=target_session_id,
            source_session_id=source_session_id,
            organization_id=organization_id,
            qualification_ids=qualification_ids,
        )
    return out
