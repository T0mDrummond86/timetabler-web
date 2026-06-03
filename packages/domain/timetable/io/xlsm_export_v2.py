"""Export v2 — per-entity timetables using pre-styled v2 Excel templates (no Overall sheet).

Grid styling (borders, fills, headers, time column) lives in ``templates/export_v2_base.xlsm``
and must be edited in Excel. This module only writes data: sheet titles and merged placecards.

Each weekday block is four columns wide. Course placecards use two columns (T1 left, T2 right)
or all four when the booking is in both terms.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy.orm import Session

from ..bundle_paths import resource_path
from ..constants import NUM_DAYS, NUM_SLOTS
from ..core.class_colour import booking_colour_key
from ..core.models import Booking, Course, Room, Staff
from ..core.room_types import room_is_physical
from ..core.auto_timetable_constraints import blocked_slots_from_availability
from .backup_payload import write_backup_sheet
from .xlsm_export import (
    ExportReport,
    _bookings_by_slot,
    _bookings_for_staff_tab,
    _course_border_hex,
    _course_fill_hex,
    _entity_values,
    _staff_lane_subgroups,
    _staff_placecard_lines,
    _lecturer_label,
    placecard_subject_block,
    _resolve_week,
    _safe_sheet_name,
    _terms_of,
    _week_bookings,
)

V2_TEMPLATE_PATH = resource_path("templates", "export_v2_base.xlsm")

V2_TEMPLATE_SHEETS = (
    "Course Template v2",
    "Staff Template v2",
    "Room Template v2",
)

V2_TITLE_ROW = 1
V2_FIRST_SLOT_ROW = 3
V2_DAY_STRIDE = 5  # 4 day columns + 1 gap
V2_NUM_DAYS = NUM_DAYS  # Mon–Fri (no Saturday)
V2_DAY_FIRST_COL = 2
V2_DAY_FIRST_COLS = tuple(V2_DAY_FIRST_COL + day * V2_DAY_STRIDE for day in range(V2_NUM_DAYS))
V2_DAY_BLOCK_WIDTH = 4
V2_LANE_WIDTH = 2  # T1-only or T2-only placecards span two columns within the day block
V2_LAST_COL = V2_DAY_FIRST_COLS[-1] + V2_DAY_BLOCK_WIDTH - 1
V2_GRID_LAST_ROW = V2_FIRST_SLOT_ROW + NUM_SLOTS - 1
V2_FOOTER_START_ROW = V2_GRID_LAST_ROW + 1

# Staff sheet: lecturer hours summary in columns AA / AB (top of sheet, row 1).
V2_SUMMARY_CLASS_COL = 27
V2_SUMMARY_HOURS_COL = 28
V2_STAFF_HOURS_SUMMARY_HEADER_ROW = 1
V2_SUMMARY_HEADER_ROW = V2_STAFF_HOURS_SUMMARY_HEADER_ROW
V2_SUMMARY_FIRST_DATA_ROW = V2_STAFF_HOURS_SUMMARY_HEADER_ROW + 1

# Placecard styling only (booking cards, not the grid template).
V2_PLACECARD_FONT = Font(name="Calibri", size=12, bold=True, color="FF1A1A1A")
V2_PLACECARD_ALIGN = Alignment(horizontal="left", vertical="top", wrap_text=True)
V2_SUMMARY_HEADER_FILL = PatternFill(
    start_color="FF374151", end_color="FF374151", fill_type="solid"
)
V2_SUMMARY_DATA_FILL = PatternFill(
    start_color="FFFFFFFF", end_color="FFFFFFFF", fill_type="solid"
)
V2_SUMMARY_DATA_ALT_FILL = PatternFill(
    start_color="FFF9FAFB", end_color="FFF9FAFB", fill_type="solid"
)
V2_SUMMARY_TOTAL_FILL = PatternFill(
    start_color="FFF3F4F6", end_color="FFF3F4F6", fill_type="solid"
)
V2_SUMMARY_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
V2_SUMMARY_BODY_FONT = Font(name="Calibri", size=11, bold=False, color="FF1A1A1A")
V2_SUMMARY_TOTAL_FONT = Font(name="Calibri", size=11, bold=True, color="FF1A1A1A")
V2_SUMMARY_ALIGN = Alignment(horizontal="left", vertical="center", wrap_text=True)
V2_SUMMARY_HOURS_ALIGN = Alignment(horizontal="right", vertical="center")
V2_SUMMARY_CLASS_COL_WIDTH = 32
V2_SUMMARY_HOURS_COL_WIDTH = 11

# Staff timetable: blocked-times grid only (not non-teaching day).
V2_BLOCKED_SLOT_FILL = PatternFill(
    start_color="FFF3E8FF", end_color="FFF3E8FF", fill_type="solid"
)
_SUMMARY_BORDER_COLOR = "FFD1D5DB"
_SUMMARY_BORDER_STRONG = "FF9CA3AF"


def _ranges_intersect(a_min: int, a_max: int, b_min: int, b_max: int) -> bool:
    return a_min <= b_max and a_max >= b_min


@dataclass
class ExportV2Report(ExportReport):
    """Same counters as v1 export; no Overall courses_written fields used."""

    template_path: Path | None = None
    colour_by_class: bool = True


def _v2_slot_row(slot: int) -> int:
    return V2_FIRST_SLOT_ROW + slot


def _v2_booking_rows(b: Booking) -> tuple[int, int]:
    """Map booking slots to worksheet rows (end_slot is exclusive)."""
    top_row = _v2_slot_row(b.start_slot)
    end_slot = b.end_slot if b.end_slot > b.start_slot else b.start_slot + 1
    bot_row = _v2_slot_row(end_slot - 1)
    return top_row, max(top_row, bot_row)


def _v2_lane_cols(day: int, t1: bool, t2: bool) -> tuple[int, int]:
    """Inclusive column range for a placecard within a 4-column day block.

    - Semester (T1 and T2): all four columns.
    - T1 only: left two columns of the block.
    - T2 only: right two columns of the block.
    """
    if not (0 <= day < V2_NUM_DAYS):
        start = V2_DAY_FIRST_COLS[0]
        return start, start + V2_DAY_BLOCK_WIDTH - 1
    start = V2_DAY_FIRST_COLS[day]
    if t1 and t2:
        return start, start + V2_DAY_BLOCK_WIDTH - 1
    if t1:
        return start, start + V2_LANE_WIDTH - 1
    if t2:
        return start + V2_LANE_WIDTH, start + V2_DAY_BLOCK_WIDTH - 1
    return start, start + V2_DAY_BLOCK_WIDTH - 1


def _v2_last_slot_row() -> int:
    return V2_FIRST_SLOT_ROW + NUM_SLOTS - 1


def _v2_body_col_range() -> tuple[int, int]:
    first = V2_DAY_FIRST_COLS[0]
    last_day = V2_DAY_FIRST_COLS[-1]
    return first, last_day + V2_DAY_BLOCK_WIDTH - 1


def _v2_slot_content_cols() -> tuple[int, ...]:
    """Day-block content columns only (excludes gap/spacer columns)."""
    cols: list[int] = []
    for day in range(V2_NUM_DAYS):
        start = V2_DAY_FIRST_COLS[day]
        cols.extend(range(start, start + V2_DAY_BLOCK_WIDTH))
    return tuple(cols)


def _unmerge_intersecting(
    ws,
    top_row: int,
    bot_row: int,
    col_start: int,
    col_end: int,
) -> None:
    """Split merges overlapping the target rectangle."""
    for merged in list(ws.merged_cells.ranges):
        if _ranges_intersect(merged.min_row, merged.max_row, top_row, bot_row) and _ranges_intersect(
            merged.min_col, merged.max_col, col_start, col_end
        ):
            ws.unmerge_cells(str(merged))


def _clear_v2_cell_value(ws, row: int, col: int) -> None:
    """Clear cell value only; preserve template formatting."""
    cell = ws.cell(row=row, column=col)
    if isinstance(cell, MergedCell):
        return
    cell.value = None


def _unmerge_v2_body(ws) -> None:
    """Remove booking-area merges from the slot grid."""
    min_col, max_col = _v2_body_col_range()
    top, bot = V2_FIRST_SLOT_ROW, _v2_last_slot_row()
    for merged in list(ws.merged_cells.ranges):
        if _ranges_intersect(merged.min_row, merged.max_row, top, bot) and _ranges_intersect(
            merged.min_col, merged.max_col, min_col, max_col
        ):
            ws.unmerge_cells(str(merged))


def _clear_v2_body(ws) -> None:
    """Clear prior booking text from day columns; do not alter grid styles."""
    for row in range(V2_FIRST_SLOT_ROW, _v2_last_slot_row() + 1):
        for col in _v2_slot_content_cols():
            _clear_v2_cell_value(ws, row, col)


def _clear_v2_footer(ws) -> None:
    """Clear footer text only (values), preserving template formatting."""
    last_col = _v2_body_col_range()[1]
    for row in range(V2_FOOTER_START_ROW, ws.max_row + 1):
        for col in range(1, last_col + 1):
            _clear_v2_cell_value(ws, row, col)


def _unmerge_v2_staff_summary(ws) -> None:
    for merged in list(ws.merged_cells.ranges):
        if merged.min_col >= V2_SUMMARY_CLASS_COL and merged.max_col <= V2_SUMMARY_HOURS_COL:
            ws.unmerge_cells(str(merged))


def _clear_v2_staff_summary(ws) -> None:
    """Clear staff hours summary columns (AA–AB), including legacy copies below the grid."""
    _unmerge_v2_staff_summary(ws)
    last_row = max(ws.max_row, V2_SUMMARY_HEADER_ROW + 40)
    for row in range(1, last_row + 1):
        for col in (V2_SUMMARY_CLASS_COL, V2_SUMMARY_HOURS_COL):
            _clear_v2_cell_value(ws, row, col)


def _summary_border(
    *,
    top=None,
    bottom=None,
    left=None,
    right=None,
) -> Border:
    thin = Side(style="thin", color=_SUMMARY_BORDER_COLOR)
    return Border(
        top=top or thin,
        bottom=bottom or thin,
        left=left or thin,
        right=right or thin,
    )


def _summary_cols() -> tuple[int, int]:
    return V2_SUMMARY_CLASS_COL, V2_SUMMARY_HOURS_COL


def _apply_v2_summary_cell(
    cell,
    *,
    role: str,
    data_index: int = 0,
    table_top: bool = False,
    table_bottom: bool = False,
    is_left: bool = False,
    is_right: bool = False,
) -> None:
    """Apply fills, fonts, borders for one cell in the hours summary table."""
    strong = Side(style="thin", color=_SUMMARY_BORDER_STRONG)
    thin = Side(style="thin", color=_SUMMARY_BORDER_COLOR)
    top = strong if table_top else thin
    bottom = strong if table_bottom else thin
    left = strong if is_left else thin
    right = strong if is_right else thin

    if role == "header":
        cell.font = V2_SUMMARY_HEADER_FONT
        cell.fill = V2_SUMMARY_HEADER_FILL
        cell.alignment = (
            V2_SUMMARY_ALIGN if cell.column == V2_SUMMARY_CLASS_COL else V2_SUMMARY_HOURS_ALIGN
        )
        cell.border = _summary_border(top=top, bottom=bottom, left=left, right=right)
        return

    if role == "total":
        cell.font = V2_SUMMARY_TOTAL_FONT
        cell.fill = V2_SUMMARY_TOTAL_FILL
        cell.alignment = (
            V2_SUMMARY_ALIGN if cell.column == V2_SUMMARY_CLASS_COL else V2_SUMMARY_HOURS_ALIGN
        )
        cell.border = _summary_border(top=strong, bottom=bottom, left=left, right=right)
        return

    if role == "spacer":
        cell.font = V2_SUMMARY_BODY_FONT
        cell.fill = V2_SUMMARY_DATA_FILL
        cell.alignment = V2_SUMMARY_ALIGN
        cell.border = Border(left=left, right=right)
        return

    # data row
    cell.font = V2_SUMMARY_BODY_FONT
    cell.fill = V2_SUMMARY_DATA_ALT_FILL if data_index % 2 else V2_SUMMARY_DATA_FILL
    cell.alignment = (
        V2_SUMMARY_ALIGN if cell.column == V2_SUMMARY_CLASS_COL else V2_SUMMARY_HOURS_ALIGN
    )
    cell.border = _summary_border(top=top, bottom=bottom, left=left, right=right)


def _format_v2_summary_columns(ws) -> None:
    from openpyxl.utils import get_column_letter

    for col in (V2_SUMMARY_CLASS_COL, V2_SUMMARY_HOURS_COL):
        letter = get_column_letter(col)
        dim = ws.column_dimensions[letter]
        dim.hidden = False
        dim.width = (
            V2_SUMMARY_CLASS_COL_WIDTH
            if col == V2_SUMMARY_CLASS_COL
            else V2_SUMMARY_HOURS_COL_WIDTH
        )


def _v2_summary_spacer_row(ws, row: int, col_l: int, col_r: int) -> int:
    for col, is_left, is_right in ((col_l, True, False), (col_r, False, True)):
        spacer = ws.cell(row=row, column=col, value=None)
        _apply_v2_summary_cell(spacer, role="spacer", is_left=is_left, is_right=is_right)
    return row + 1


def _v2_summary_hours_row(
    ws,
    row: int,
    col_l: int,
    col_r: int,
    label: str,
    hours: float | None,
    *,
    role: str = "data",
    data_index: int = 0,
    table_top: bool = False,
    table_bottom: bool = False,
) -> int:
    c_cell = ws.cell(row=row, column=col_l, value=label)
    _apply_v2_summary_cell(
        c_cell,
        role=role,
        data_index=data_index,
        table_top=table_top,
        table_bottom=table_bottom,
        is_left=True,
    )
    h_cell = ws.cell(row=row, column=col_r, value=None if hours is None else round(hours, 2))
    if hours is not None:
        h_cell.number_format = "0.00"
    _apply_v2_summary_cell(
        h_cell,
        role=role,
        data_index=data_index,
        table_top=table_top,
        table_bottom=table_bottom,
        is_right=True,
    )
    return row + 1


def _render_v2_staff_hours_summary(
    ws,
    session: Session,
    staff_id: int,
    bookings: list[Booking],
) -> None:
    """Class / hours table in columns AA–AB with workload footer and FTE variance."""
    from ..core.staff_hours import (
        class_hours_summary_for_staff_export,
        staff_v2_hours_summary_footer,
    )

    _clear_v2_staff_summary(ws)
    class_rows, _class_total = class_hours_summary_for_staff_export(
        session, staff_id, bookings
    )
    extra_rows, grand_total, variance = staff_v2_hours_summary_footer(
        session, staff_id, bookings
    )
    _format_v2_summary_columns(ws)

    col_l, col_r = _summary_cols()
    hdr_row = V2_SUMMARY_HEADER_ROW

    hdr_class = ws.cell(row=hdr_row, column=col_l, value="Class")
    _apply_v2_summary_cell(
        hdr_class, role="header", table_top=True, is_left=True,
    )
    hdr_hours = ws.cell(row=hdr_row, column=col_r, value="Hours")
    _apply_v2_summary_cell(
        hdr_hours, role="header", table_top=True, is_right=True,
    )

    row = V2_SUMMARY_FIRST_DATA_ROW
    for idx, (label, hours) in enumerate(class_rows):
        row = _v2_summary_hours_row(
            ws, row, col_l, col_r, label, hours, role="data", data_index=idx
        )

    if class_rows:
        row = _v2_summary_spacer_row(ws, row, col_l, col_r)

    for idx, (label, hours) in enumerate(extra_rows):
        row = _v2_summary_hours_row(
            ws,
            row,
            col_l,
            col_r,
            label,
            hours,
            role="data",
            data_index=len(class_rows) + idx,
        )

    row = _v2_summary_spacer_row(ws, row, col_l, col_r)
    table_top = not class_rows and not extra_rows
    row = _v2_summary_hours_row(
        ws,
        row,
        col_l,
        col_r,
        "Total",
        grand_total,
        role="total",
        table_top=table_top,
        table_bottom=variance is None,
    )

    if variance is not None:
        _v2_summary_hours_row(
            ws,
            row,
            col_l,
            col_r,
            "Over / under",
            variance,
            role="total",
            table_bottom=True,
        )


def _draw_v2_placecard(
    ws,
    top_row: int,
    bot_row: int,
    col_start: int,
    col_end: int,
    lines: tuple[str, str, str],
    tint_key: str,
) -> None:
    """Merged placecard for a booking (styles apply to the card only)."""
    top_row, bot_row = min(top_row, bot_row), max(top_row, bot_row)
    col_start, col_end = min(col_start, col_end), max(col_start, col_end)
    _unmerge_intersecting(ws, top_row, bot_row, col_start, col_end)
    text = "\n".join(x for x in lines if x)
    fill = PatternFill(
        start_color=_course_fill_hex(tint_key),
        end_color=_course_fill_hex(tint_key),
        fill_type="solid",
    )
    border_side = Side(border_style="medium", color=_course_border_hex(tint_key))
    border = Border(top=border_side, bottom=border_side, left=border_side, right=border_side)

    anchor = ws.cell(row=top_row, column=col_start, value=text)
    anchor.fill = fill
    anchor.font = V2_PLACECARD_FONT
    anchor.border = border
    anchor.alignment = V2_PLACECARD_ALIGN
    for row in range(top_row, bot_row + 1):
        for col in range(col_start, col_end + 1):
            cell = ws.cell(row=row, column=col)
            if isinstance(cell, MergedCell):
                continue
            cell.fill = fill
            if row == top_row and col == col_start:
                continue
            cell.border = border
    ws.merge_cells(
        start_row=top_row,
        end_row=bot_row,
        start_column=col_start,
        end_column=col_end,
    )


def _set_v2_title(ws, title: str) -> None:
    """Set sheet title text in the template's merged title cell (no style changes)."""
    ws.cell(row=V2_TITLE_ROW, column=1, value=title)


def _strip_saturday_from_sheet(ws) -> None:
    """Clear Saturday column values beyond the Mon–Fri grid (values only)."""
    sat_start = V2_DAY_FIRST_COL + V2_NUM_DAYS * V2_DAY_STRIDE
    for merged in list(ws.merged_cells.ranges):
        if merged.min_col >= sat_start:
            ws.unmerge_cells(str(merged))
    for row in range(1, ws.max_row + 1):
        for col in range(sat_start, ws.max_column + 1):
            _clear_v2_cell_value(ws, row, col)


def _paint_v2_staff_blocked_slots(ws, session: Session, staff_id: int) -> None:
    """Very light purple fill for Staff-tab blocked-times grid slots (not non-teaching day)."""
    staff = session.get(Staff, staff_id)
    if staff is None:
        return
    blocked = blocked_slots_from_availability(staff, session)
    if not blocked:
        return
    for day, slot in blocked:
        if not (0 <= day < V2_NUM_DAYS and 0 <= slot < NUM_SLOTS):
            continue
        row = _v2_slot_row(slot)
        col_start, col_end = _v2_lane_cols(day, True, True)
        for col in range(col_start, col_end + 1):
            cell = ws.cell(row=row, column=col)
            if isinstance(cell, MergedCell):
                continue
            cell.fill = V2_BLOCKED_SLOT_FILL


def _render_v2_course_tab(
    ws, title: str, bookings: list[Booking], *, colour_by_class: bool
) -> None:
    _strip_saturday_from_sheet(ws)
    _set_v2_title(ws, title)
    _unmerge_v2_body(ws)
    _clear_v2_body(ws)
    _clear_v2_footer(ws)

    for b in bookings:
        if not (0 <= b.day < V2_NUM_DAYS):
            continue
        top_row, bot_row = _v2_booking_rows(b)
        t1, t2 = _terms_of(b)
        if not t1 and not t2:
            continue
        col_start, col_end = _v2_lane_cols(b.day, t1, t2)
        lane_term = "t1" if t1 and not t2 else ("t2" if t2 and not t1 else None)
        lines = (
            placecard_subject_block(b, term=lane_term),
            (b.room.code if b.room else "") or "",
            _lecturer_label(b),
        )
        tint = booking_colour_key(b, by_class=colour_by_class)
        _draw_v2_placecard(ws, top_row, bot_row, col_start, col_end, lines, tint)


def _render_v2_staff_tab(
    ws,
    title: str,
    bookings: list[Booking],
    *,
    view_staff_id: int,
    session: Session,
    colour_by_class: bool,
) -> None:
    _strip_saturday_from_sheet(ws)
    _set_v2_title(ws, title)
    _unmerge_v2_body(ws)
    _clear_v2_body(ws)
    _clear_v2_footer(ws)

    _paint_v2_staff_blocked_slots(ws, session, view_staff_id)

    for group in _bookings_by_slot(bookings):
        b0 = group[0]
        if not (0 <= b0.day < V2_NUM_DAYS):
            continue
        top_row, bot_row = _v2_booking_rows(b0)
        for (t1, t2), lane_bookings in _staff_lane_subgroups(group, view_staff_id):
            if not t1 and not t2:
                continue
            col_start, col_end = _v2_lane_cols(b0.day, t1, t2)
            lane_term = "t1" if t1 and not t2 else ("t2" if t2 and not t1 else None)
            lines, tint = _staff_placecard_lines(
                lane_bookings,
                view_staff_id=view_staff_id,
                colour_by_class=colour_by_class,
                term=lane_term,
            )
            _draw_v2_placecard(ws, top_row, bot_row, col_start, col_end, lines, tint)

    _render_v2_staff_hours_summary(ws, session, view_staff_id, bookings)


def _render_v2_room_tab(
    ws, title: str, bookings: list[Booking], *, colour_by_class: bool
) -> None:
    _strip_saturday_from_sheet(ws)
    _set_v2_title(ws, title)
    _unmerge_v2_body(ws)
    _clear_v2_body(ws)
    _clear_v2_footer(ws)

    for b in bookings:
        if not (0 <= b.day < V2_NUM_DAYS):
            continue
        top_row, bot_row = _v2_booking_rows(b)
        col_start, col_end = _v2_lane_cols(b.day, True, True)
        lines = (
            placecard_subject_block(b),
            _lecturer_label(b),
            (b.course.code if b.course else "") or "",
        )
        tint = booking_colour_key(b, by_class=colour_by_class)
        _draw_v2_placecard(ws, top_row, bot_row, col_start, col_end, lines, tint)


def _generate_v2_entity_tabs(
    wb,
    session: Session,
    week_id: int,
    report: ExportV2Report,
    *,
    colour_by_class: bool,
    timetable_session_id: int | None = None,
) -> None:
    from ..core.sidebar_order import ordered_courses, ordered_staff

    bookings = _week_bookings(session, week_id)
    used_names = set(wb.sheetnames)

    course_t = wb["Course Template v2"] if "Course Template v2" in wb.sheetnames else None
    staff_t = wb["Staff Template v2"] if "Staff Template v2" in wb.sheetnames else None
    room_t = wb["Room Template v2"] if "Room Template v2" in wb.sheetnames else None

    if course_t is not None:
        for c in ordered_courses(
            session, include_block_cohorts=True, timetable_session_id=timetable_session_id
        ):
            ws = wb.copy_worksheet(course_t)
            ws.title = _safe_sheet_name(c.code, used_names)
            _render_v2_course_tab(
                ws,
                c.code,
                [b for b in bookings if b.course_id == c.id],
                colour_by_class=colour_by_class,
            )
            report.course_tabs += 1

    if staff_t is not None:
        for s in ordered_staff(session, timetable_session_id=timetable_session_id):
            ws = wb.copy_worksheet(staff_t)
            ws.title = _safe_sheet_name(s.name, used_names)
            staff_bookings = _bookings_for_staff_tab(bookings, s.id)
            _render_v2_staff_tab(
                ws,
                s.name,
                staff_bookings,
                view_staff_id=s.id,
                session=session,
                colour_by_class=colour_by_class,
            )
            report.staff_tabs += 1

    if room_t is not None:
        room_q = session.query(Room).order_by(Room.code)
        if timetable_session_id is not None:
            room_q = room_q.filter(Room.timetable_session_id == timetable_session_id)
        rooms = [r for r in room_q.all() if room_is_physical(r)]
        for r in rooms:
            ws = wb.copy_worksheet(room_t)
            ws.title = _safe_sheet_name(r.code, used_names)
            _render_v2_room_tab(
                ws,
                r.code,
                [b for b in bookings if b.room_id == r.id],
                colour_by_class=colour_by_class,
            )
            report.room_tabs += 1

    for tpl_name in V2_TEMPLATE_SHEETS:
        if tpl_name in wb.sheetnames:
            del wb[tpl_name]


def _apply_v2_readonly_protection(wb) -> None:
    """Protect all worksheets so exported timetables open read-only in Excel."""
    from openpyxl.workbook.protection import WorkbookProtection

    for ws in wb.worksheets:
        prot = ws.protection
        prot.enable()
        # Allow viewing/selecting cells; locked cells cannot be edited once protected.
        prot.selectLockedCells = True
        prot.selectUnlockedCells = True
    wb.security = WorkbookProtection(lockStructure=True)


def write_v2(
    session: Session,
    out_path: str | Path,
    *,
    template_path: str | Path | None = None,
    week_id: int | None = None,
    colour_by_class: bool | None = None,
    timetable_session_id: int | None = None,
) -> ExportV2Report:
    """Export course / staff / room tabs using the v2 templates (no Overall)."""
    from ..core.display_settings import resolve_export_colour_by_class

    colour_by_class = resolve_export_colour_by_class(colour_by_class)
    template_path = Path(template_path or V2_TEMPLATE_PATH)
    out_path = Path(out_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"v2 export template not found: {template_path}")

    probe = load_workbook(template_path, read_only=True)
    try:
        missing = [n for n in V2_TEMPLATE_SHEETS if n not in probe.sheetnames]
        if missing:
            raise ValueError(f"Template missing sheet(s): {', '.join(missing)}")
    finally:
        probe.close()

    if template_path.resolve() != out_path.resolve():
        shutil.copyfile(template_path, out_path)

    wb = load_workbook(out_path, keep_vba=True)
    report = ExportV2Report(
        out_path=out_path,
        template_path=template_path,
        colour_by_class=colour_by_class,
    )

    for name in list(wb.sheetnames):
        if name not in V2_TEMPLATE_SHEETS:
            del wb[name]
            report.sheets_removed.append(name)

    week = _resolve_week(session, week_id)

    for tpl_name in V2_TEMPLATE_SHEETS:
        _strip_saturday_from_sheet(wb[tpl_name])

    _generate_v2_entity_tabs(
        wb,
        session,
        week.id,
        report,
        colour_by_class=colour_by_class,
        timetable_session_id=timetable_session_id,
    )
    report.bookings = len(_week_bookings(session, week.id))
    write_backup_sheet(wb, session, timetable_session_id=timetable_session_id)
    _apply_v2_readonly_protection(wb)
    wb.save(out_path)
    return report
