"""Build an Excel template for capturing lecturer preferences.

One tab per lecturer in `Staff`, each carrying:
  - six class preferences split into:
      2x first preference, 2x second preference, 2x third preference
  - each preference row has two dropdowns:
      Qualification, then Class (filtered by Qualification)
  - a single non-teaching day picked from a dropdown
  - the number of delivery hours the lecturer is asking for, pre-filled with
    the 21 hours one FTE carries, so most people only have to change it
  - a free-text box for anything the fixed sections cannot say
  - a blocked-times grid (Mon–Sat × half-hour slots), ending at 21:30

A hidden `_classes` sheet holds validation data.

Everything is scoped to one timetable session. On the desktop that is implicit
-- one `*.db` file holds one session -- but the web app keeps every session in
one database, so an unscoped query put every lecturer, qualification and class
in the whole organisation into the workbook. Pass `timetable_session_id` there;
leaving it None keeps the desktop's whole-file behaviour.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS, slot_to_time
from ..core.models import Qualification, Staff, Unit, UnitQualification


CLASS_LIST_SHEET = "_classes"

#: Hours one FTE delivers, the same figure `Staff.fte` is multiplied by. Almost
#: every lecturer is asking for exactly this, so the cell arrives filled in and
#: the few who want more or less are the only ones who have to type.
DEFAULT_REQUESTED_HOURS = 21


def _safe_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names: ≤31 chars, no [\\:/?*[]] characters, must be unique."""
    bad = set("[]:*?/\\")
    cleaned = "".join("_" if ch in bad else ch for ch in str(name)).strip()
    cleaned = cleaned[:31] or "Sheet"
    base = cleaned
    n = 1
    while cleaned in used:
        n += 1
        suffix = f" ({n})"
        cleaned = (base[: 31 - len(suffix)] + suffix).strip()
    used.add(cleaned)
    return cleaned


def _populate_class_list_sheet(
    ws,
    qualifications: list[Qualification],
    classes: list[Unit],
    unit_to_quals: dict[int, list[str]],
) -> tuple[int, int]:
    """Hidden sheet backing Qualification/Class dependent dropdowns.

    Returns:
      (qualifications_row_count, qual_class_map_row_count)
    """
    ws["A1"] = "Qualification list"
    ws["A1"].font = Font(bold=True)
    ws["C1"] = "Qualification"
    ws["D1"] = "Class"
    ws["C1"].font = Font(bold=True)
    ws["D1"].font = Font(bold=True)

    qual_names = [q.name for q in qualifications]
    for i, qname in enumerate(qual_names, start=2):
        ws.cell(row=i, column=1, value=qname)

    map_row = 2
    for qname in qual_names:
        q_classes = [u.name for u in classes if qname in unit_to_quals.get(u.id, [])]
        for cname in q_classes:
            ws.cell(row=map_row, column=3, value=qname)
            ws.cell(row=map_row, column=4, value=cname)
            map_row += 1

    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["C"].width = 36
    ws.column_dimensions["D"].width = 36
    ws.sheet_state = "hidden"
    return len(qual_names), max(0, map_row - 2)


def _populate_lecturer_sheet(ws, staff: Staff, n_quals: int, n_map_rows: int) -> None:
    title_font = Font(name="Tahoma", size=18, bold=True)
    section_font = Font(name="Calibri", size=12, bold=True)
    header_font = Font(name="Calibri", size=11, bold=True, color="FF1F2937")
    header_fill = PatternFill(start_color="FFE9ECEF", end_color="FFE9ECEF", fill_type="solid")
    grid_fill = PatternFill(start_color="FFFAFAFA", end_color="FFFAFAFA", fill_type="solid")
    border_side = Side(border_style="thin", color="FFD0D7DE")
    border = Border(top=border_side, bottom=border_side, left=border_side, right=border_side)
    centre = Alignment(horizontal="center", vertical="center")

    ws["A1"] = f"Preferences — {staff.name}"
    ws["A1"].font = title_font
    ws.row_dimensions[1].height = 28

    # ---- Class preferences ----
    ws["A3"] = "Class preferences (2x first, 2x second, 2x third)"
    ws["A3"].font = section_font
    ws["A5"] = "Priority"
    ws["B5"] = "Qualification"
    ws["C5"] = "Class"
    for c in (ws["A5"], ws["B5"], ws["C5"]):
        c.font = header_font
        c.fill = header_fill
        c.alignment = centre
        c.border = border

    qual_dv = None
    if n_quals > 0:
        qual_formula = f"={CLASS_LIST_SHEET}!$A$2:$A${n_quals + 1}"
        qual_dv = DataValidation(type="list", formula1=qual_formula, allow_blank=True)
        qual_dv.error = "Please pick a qualification from the list."
        qual_dv.errorTitle = "Unknown qualification"
        ws.add_data_validation(qual_dv)

    class_dv = None
    if n_map_rows > 0:
        # Filter class list by selected qualification in column B.
        class_formula = (
            f"=OFFSET({CLASS_LIST_SHEET}!$D$2,"
            f"MATCH($B6,{CLASS_LIST_SHEET}!$C$2:$C${n_map_rows + 1},0)-1,"
            f"0,"
            f"COUNTIF({CLASS_LIST_SHEET}!$C$2:$C${n_map_rows + 1},$B6),1)"
        )
        class_dv = DataValidation(type="list", formula1=class_formula, allow_blank=True)
        class_dv.error = "Please pick a class from the list."
        class_dv.errorTitle = "Unknown class"
        ws.add_data_validation(class_dv)

    priorities = ("First", "First", "Second", "Second", "Third", "Third")
    for idx, priority in enumerate(priorities, start=1):
        row = 5 + idx
        ws.cell(row=row, column=1, value=priority).alignment = centre
        ws.cell(row=row, column=1).border = border
        qual_cell = ws.cell(row=row, column=2)
        qual_cell.border = border
        qual_cell.alignment = centre
        class_cell = ws.cell(row=row, column=3)
        class_cell.border = border
        class_cell.alignment = centre
        if qual_dv is not None:
            qual_dv.add(qual_cell)
        if class_dv is not None:
            class_dv.add(class_cell)

    # ---- Non-teaching day ----
    nt_row = 14
    ws.cell(row=nt_row, column=1, value="Non-teaching day").font = section_font
    day_dv = DataValidation(
        type="list",
        formula1='"' + ",".join(DAYS) + '"',
        allow_blank=True,
    )
    day_dv.error = "Pick a day of the week."
    day_dv.errorTitle = "Unknown day"
    ws.add_data_validation(day_dv)
    day_cell = ws.cell(row=nt_row, column=2)
    day_cell.border = border
    day_cell.alignment = centre
    day_dv.add(day_cell)

    # ---- Requested delivery hours ----
    # Section headings sit alone on their row, as the ones above and below do:
    # column A is only 14 wide (it has to fit "08:00–08:30" in the grid), so a
    # heading with anything beside it would be clipped to half a word.
    hint_font = Font(name="Calibri", size=9, italic=True, color="FF555555")
    hint_align = Alignment(horizontal="left", vertical="center")

    hours_row = nt_row + 2
    ws.cell(row=hours_row, column=1, value="Delivery hours requested").font = section_font
    hours_cell = ws.cell(row=hours_row + 1, column=2, value=DEFAULT_REQUESTED_HOURS)
    hours_cell.border = border
    hours_cell.alignment = centre
    hours_dv = DataValidation(
        type="decimal", operator="between", formula1=0, formula2=40, allow_blank=True
    )
    hours_dv.error = "Enter the number of hours you are asking to deliver each week."
    hours_dv.errorTitle = "Hours out of range"
    ws.add_data_validation(hours_dv)
    hours_dv.add(hours_cell)
    hours_hint = ws.cell(
        row=hours_row + 1,
        column=3,
        value=f"Hours per week. {DEFAULT_REQUESTED_HOURS} is a full load — change it if yours differs.",
    )
    hours_hint.font = hint_font
    hours_hint.alignment = hint_align

    # ---- Additional notes ----
    notes_row = hours_row + 3
    ws.cell(row=notes_row, column=1, value="Additional notes").font = section_font
    notes_hint = ws.cell(
        row=notes_row + 1,
        column=1,
        value="Anything the sections above cannot say — job-share, travel between campuses, study leave.",
    )
    notes_hint.font = hint_font
    notes_hint.alignment = hint_align
    # One merged box rather than ruled lines: a lecturer with two sentences and
    # a lecturer with ten both get somewhere obvious to put them.
    notes_top = notes_row + 2
    notes_bottom = notes_top + 5
    notes_last_col = get_column_letter(1 + NUM_DAYS)
    ws.merge_cells(f"A{notes_top}:{notes_last_col}{notes_bottom}")
    notes_box = ws.cell(row=notes_top, column=1)
    notes_box.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    for r in range(notes_top, notes_bottom + 1):
        ws.row_dimensions[r].height = 18
        for c in range(1, 2 + NUM_DAYS):
            ws.cell(row=r, column=c).border = border

    # ---- Blocked times grid ----
    grid_top = notes_bottom + 2
    ws.cell(row=grid_top, column=1, value="Blocked times — write X in slots you cannot teach").font = section_font
    # Day headers.
    header_row = grid_top + 2
    ws.cell(row=header_row, column=1, value="Time")
    for d, name in enumerate(DAYS):
        c = ws.cell(row=header_row, column=2 + d, value=name)
        c.font = header_font
        c.fill = header_fill
        c.alignment = centre
        c.border = border
    ws.cell(row=header_row, column=1).font = header_font
    ws.cell(row=header_row, column=1).fill = header_fill
    ws.cell(row=header_row, column=1).alignment = centre
    ws.cell(row=header_row, column=1).border = border

    # Time rows.
    for s in range(max(0, NUM_SLOTS - 1)):
        row = header_row + 1 + s
        time_label = (
            f"{slot_to_time(s).strftime('%H:%M')}–"
            f"{slot_to_time(s + 1).strftime('%H:%M')}"
        )
        c = ws.cell(row=row, column=1, value=time_label)
        c.alignment = centre
        c.font = Font(name="Calibri", size=9, color="FF555555")
        c.border = border
        for d in range(NUM_DAYS):
            cell = ws.cell(row=row, column=2 + d)
            cell.fill = grid_fill
            cell.border = border
            cell.alignment = centre
        ws.row_dimensions[row].height = 16

    # Column widths.
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 32
    for d in range(NUM_DAYS):
        ws.column_dimensions[get_column_letter(2 + d)].width = max(
            ws.column_dimensions[get_column_letter(2 + d)].width or 0, 11
        )

    # Columns A and B are shared: A carries the priority labels and the time
    # labels, B carries the qualification names and Monday. B is set wide for
    # the qualification names, which is more than Monday needs and harmless.
    ws.freeze_panes = "B6"


def write_lecturer_preferences_template(
    session: Session,
    out_path: str | Path,
    *,
    timetable_session_id: int | None = None,
) -> Path:
    """Build the workbook. Returns the saved path.

    ``timetable_session_id`` restricts the lecturers, qualifications and classes
    to one session. None means the whole database, which is right for a desktop
    file and wrong for anything sharing a database.
    """
    out_path = Path(out_path)
    wb = Workbook()
    # Use the default sheet for the class-list, then add lecturer sheets.
    classes_ws = wb.active
    classes_ws.title = CLASS_LIST_SHEET

    def scoped(query, model):
        if timetable_session_id is None:
            return query
        return query.filter(model.timetable_session_id == timetable_session_id)

    classes = scoped(session.query(Unit), Unit).order_by(Unit.name).all()
    qualifications = (
        scoped(session.query(Qualification), Qualification).order_by(Qualification.name).all()
    )
    # Joined through Qualification rather than filtered on the link table, which
    # carries no session of its own.
    unit_to_quals: dict[int, list[str]] = {}
    for unit_id, qname in (
        scoped(
            session.query(UnitQualification.unit_id, Qualification.name).join(
                Qualification, Qualification.id == UnitQualification.qualification_id
            ),
            Qualification,
        ).all()
    ):
        unit_to_quals.setdefault(unit_id, []).append(qname)
    n_quals, n_map_rows = _populate_class_list_sheet(
        classes_ws, qualifications, classes, unit_to_quals
    )

    used = {CLASS_LIST_SHEET}
    staff_rows = scoped(session.query(Staff), Staff).order_by(Staff.name).all()
    for s in staff_rows:
        sheet_name = _safe_sheet_name(s.name, used)
        ws = wb.create_sheet(sheet_name)
        _populate_lecturer_sheet(ws, s, n_quals, n_map_rows)

    if not staff_rows:
        # Need at least one visible sheet.
        placeholder = wb.create_sheet("(no staff)")
        placeholder["A1"] = "No staff in this session — add lecturers in the app first."

    wb.save(out_path)
    return out_path
