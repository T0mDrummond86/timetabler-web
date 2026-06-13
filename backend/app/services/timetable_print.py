"""PDF print timetables (desktop print preview parity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.io.timetable_print_layout import PrintEntitySpec, PrintJobKind, list_print_entities
from timetable.io.timetable_print_pdf import render_timetable_print_pdf

from .timetable_grid import get_repeating_week


def week_label_for_print(db: Session, timetable_session_id: int) -> str | None:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return None
    label = (week.label or "").strip()
    return label or f"Week {week.week_number}"


def print_entity_list(
    db: Session,
    *,
    timetable_session_id: int,
    kind: PrintJobKind,
) -> list[dict]:
    rows = list_print_entities(db, timetable_session_id=timetable_session_id, kind=kind)
    out: list[dict] = []
    for spec in rows:
        item: dict = {"id": spec.entity_id, "label": spec.label}
        if kind == "course_staff":
            item["entity_kind"] = spec.kind
        out.append(item)
    return out


def _entity_specs_for_print(
    kind: PrintJobKind,
    entities: list[dict],
) -> list[PrintEntitySpec]:
    specs: list[PrintEntitySpec] = []
    for row in entities:
        entity_id = int(row["id"])
        label = str(row["label"])
        if kind == "course_staff":
            entity_kind = row.get("entity_kind")
            if entity_kind not in ("course", "staff"):
                raise ValueError("Each selected timetable must include entity_kind (course or staff)")
            specs.append(PrintEntitySpec(kind=entity_kind, entity_id=entity_id, label=label))
        elif kind == "changed_courses":
            specs.append(PrintEntitySpec(kind="course", entity_id=entity_id, label=label))
        else:
            specs.append(PrintEntitySpec(kind=kind, entity_id=entity_id, label=label))
    return specs


def export_print_timetables_pdf(
    db: Session,
    *,
    timetable_session_id: int,
    kind: PrintJobKind,
    entities: list[dict],
    term_filter: str = "all",
    colour_by_class: bool = True,
    include_index: bool = True,
) -> bytes:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    if not entities:
        raise ValueError("No timetables selected")
    specs = _entity_specs_for_print(kind, entities)
    return render_timetable_print_pdf(
        db,
        week_id=week.id,
        kind=kind,
        entities=specs,
        term_filter=term_filter,
        colour_by_class=colour_by_class,
        week_label=week_label_for_print(db, timetable_session_id),
        include_index=include_index,
    )
