"""PDF print timetables (desktop print preview parity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.io.timetable_print_layout import PrintKind, list_print_entities
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
    kind: PrintKind,
) -> list[dict]:
    return [
        {"id": eid, "label": label}
        for eid, label in list_print_entities(
            db, timetable_session_id=timetable_session_id, kind=kind
        )
    ]


def export_print_timetables_pdf(
    db: Session,
    *,
    timetable_session_id: int,
    kind: PrintKind,
    entities: list[tuple[int, str]],
    term_filter: str = "all",
    colour_by_class: bool = True,
    include_index: bool = True,
) -> bytes:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    if not entities:
        raise ValueError("No timetables selected")
    return render_timetable_print_pdf(
        db,
        week_id=week.id,
        kind=kind,
        entities=entities,
        term_filter=term_filter,
        colour_by_class=colour_by_class,
        week_label=week_label_for_print(db, timetable_session_id),
        include_index=include_index,
    )
