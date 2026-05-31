"""Build an Excel template for capturing lecturer preferences.

One tab per lecturer in `Staff`, each carrying:
  - six class preferences split into:
      2x first preference, 2x second preference, 2x third preference
  - each preference row has two dropdowns:
      Qualification, then Class (filtered by Qualification)
  - a single non-teaching day picked from a dropdown
  - a blocked-times grid (Mon–Sat × half-hour slots), ending at 21:30

A hidden `_classes` sheet holds validation data.
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

    # ---- Blocked times grid ----
    grid_top = nt_row + 5
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

    # Make `B` wider near the top to fit longer class names; reset for the
    # grid section is unnecessary because the grid uses different columns
    # too. The class-preference area only uses columns A–B, the grid uses A
    # and C..H — they don't share columns 3+.
    # Actually wait: the grid uses column 2 (B) too for Mondays. Hmm.
    # Re-do: shift the grid to start at column 2 (B = Time) and 3..8 = days,
    # so the class-preference table (cols A–B) doesn't fight for width. Done
    # below by re-laying out only if a future tweak is needed. For now both
    # share `A` (rank/time labels) and `B` (class / Monday) which is fine
    # because B is wide.
    ws.freeze_panes = "B6"


def write_lecturer_preferences_template(session: Session, out_path: str | Path) -> Path:
    """Build the workbook. Returns the saved path."""
    out_path = Path(out_path)
    wb = Workbook()
    # Use the default sheet for the class-list, then add lecturer sheets.
    classes_ws = wb.active
    classes_ws.title = CLASS_LIST_SHEET

    classes = session.query(Unit).order_by(Unit.name).all()
    qualifications = session.query(Qualification).order_by(Qualification.name).all()
    unit_to_quals: dict[int, list[str]] = {}
    for unit_id, qname in (
        session.query(UnitQualification.unit_id, Qualification.name)
        .join(Qualification, Qualification.id == UnitQualification.qualification_id)
        .all()
    ):
        unit_to_quals.setdefault(unit_id, []).append(qname)
    n_quals, n_map_rows = _populate_class_list_sheet(
        classes_ws, qualifications, classes, unit_to_quals
    )

    used = {CLASS_LIST_SHEET}
    staff_rows = session.query(Staff).order_by(Staff.name).all()
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
