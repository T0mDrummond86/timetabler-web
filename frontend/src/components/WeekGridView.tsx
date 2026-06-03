import { useState } from "react";
import { slotRangeLabel, slotToTimeLabel } from "../lib/timeUtils";
import { BookingCard, HoldingClass, TimetableGrid } from "../types";
import type { AlternatePlacementOption } from "../types";
import type { ViewKind } from "../viewKinds";
import { BookingContextMenu } from "./BookingContextMenu";
import { MIME_BOOKING, MIME_PENDING } from "./HoldingAreaPanel";
import { DEFAULT_GRID_ZOOM } from "../lib/gridZoom";

export const BASE_SLOT_HEIGHT = 28;
const HEADER_HEIGHT = 40;
const TIME_GUTTER_WIDTH = 56;

type Props = {
  grid: TimetableGrid;
  sessionId: number;
  viewKind: ViewKind;
  editable?: boolean;
  zoom?: number;
  showAlerts?: boolean;
  onMove?: (bookingId: number, column: number, startSlot: number) => void;
  onEdit?: (booking: BookingCard) => void;
  onCreateEmpty?: (day: number, startSlot: number, endSlot: number) => void;
  onPlacePending?: (item: HoldingClass, day: number, startSlot: number) => void;
  onToggleLock?: (booking: BookingCard, field: "lock_time" | "lock_staff") => void;
  onAlternateMove?: (booking: BookingCard, option: AlternatePlacementOption) => void;
  onDismissViolation?: (bookingId: number, code: string) => void;
  onDelete?: (booking: BookingCard) => void;
};

function cardTitle(b: BookingCard): string {
  const parts: string[] = [];
  if (b.external_id) parts.push(`[${b.external_id}]`);
  if (b.unit_name) parts.push(b.unit_name);
  return parts.join(" ") || `Booking #${b.id}`;
}

function cardMeta(b: BookingCard, grid: TimetableGrid): string {
  const bits: string[] = [];
  const courseViews = ["staff", "room", "day", "unassigned_lecturer"];
  if (courseViews.includes(grid.view) && b.course_code) bits.push(b.course_code);
  if (grid.view !== "staff" && grid.view !== "co_teach" && b.staff_name) {
    bits.push(b.staff_name);
  }
  if (grid.view === "co_teach" && b.staff_name) bits.push(b.staff_name);
  if (grid.view !== "room" && b.room_code) bits.push(b.room_code);
  return bits.join(" · ");
}

function termBadges(b: BookingCard): string {
  const t1 = b.in_term_1 !== false;
  const t2 = b.in_term_2 !== false;
  if (t1 && t2) return "";
  if (t1) return "T1";
  if (t2) return "T2";
  return "";
}

function slotFromClientY(
  clientY: number,
  bodyTop: number,
  numSlots: number,
  duration: number,
  slotHeight: number,
): number {
  const raw = Math.floor((clientY - bodyTop) / slotHeight);
  return Math.max(0, Math.min(numSlots - duration, raw));
}

function columnIndex(b: BookingCard, grid: TimetableGrid): number {
  if (grid.column_kind === "room" || grid.column_kind === "staff") return b.column ?? 0;
  return b.day;
}

function dayForColumn(grid: TimetableGrid, colIdx: number): number {
  if (grid.column_kind === "day") return colIdx;
  if (grid.column_kind === "room") return grid.focus_day ?? 0;
  return colIdx;
}

export function WeekGridView({
  grid,
  sessionId,
  viewKind,
  editable = false,
  zoom = DEFAULT_GRID_ZOOM,
  showAlerts = true,
  onMove,
  onEdit,
  onCreateEmpty,
  onPlacePending,
  onToggleLock,
  onAlternateMove,
  onDismissViolation,
  onDelete,
}: Props) {
  const [contextMenu, setContextMenu] = useState<{
    booking: BookingCard;
    x: number;
    y: number;
  } | null>(null);
  const slotHeight = Math.round(BASE_SLOT_HEIGHT * zoom);
  const gridHeight = grid.num_slots * slotHeight;
  const columnLabels = grid.columns.length ? grid.columns : grid.days;
  const numColumns = columnLabels.length;
  const minColWidth = grid.column_kind === "room" || grid.column_kind === "staff" ? 108 : 128;
  const colTemplate = `${TIME_GUTTER_WIDTH}px repeat(${numColumns}, minmax(${minColWidth}px, 1fr))`;

  const byColumn: BookingCard[][] = Array.from({ length: numColumns }, (_, col) =>
    grid.bookings.filter((b) => columnIndex(b, grid) === col),
  );

  function bookingDuration(bookingId: number): number {
    const b = grid.bookings.find((x) => x.id === bookingId);
    return b ? b.end_slot - b.start_slot : 1;
  }

  function onColumnDragOver(e: React.DragEvent) {
    if (!editable) return;
    const types = e.dataTransfer.types;
    if (types.includes(MIME_BOOKING) || (onPlacePending && types.includes(MIME_PENDING))) {
      e.preventDefault();
      e.dataTransfer.dropEffect = types.includes(MIME_BOOKING) ? "move" : "copy";
    }
  }

  function onColumnDrop(e: React.DragEvent, columnIdx: number) {
    if (!editable) return;
    e.preventDefault();
    const col = e.currentTarget as HTMLElement;
    const rect = col.getBoundingClientRect();

    const bookingRaw = e.dataTransfer.getData(MIME_BOOKING);
    if (bookingRaw && onMove) {
      const bookingId = Number(bookingRaw);
      const duration = bookingDuration(bookingId);
      const startSlot = slotFromClientY(
        e.clientY,
        rect.top,
        grid.num_slots,
        duration,
        slotHeight,
      );
      onMove(bookingId, columnIdx, startSlot);
      return;
    }

    if (!onPlacePending || grid.column_kind !== "day") return;
    const pendingRaw = e.dataTransfer.getData(MIME_PENDING);
    if (!pendingRaw) return;
    const item = JSON.parse(pendingRaw) as HoldingClass;
    const startSlot = slotFromClientY(
      e.clientY,
      rect.top,
      grid.num_slots,
      item.duration_slots,
      slotHeight,
    );
    onPlacePending(item, columnIdx, startSlot);
  }

  function onEmptyDoubleClick(e: React.MouseEvent, colIdx: number) {
    if (!editable || !onCreateEmpty || grid.column_kind !== "day") return;
    if ((e.target as HTMLElement).closest(".booking-card")) return;
    const col = e.currentTarget as HTMLElement;
    const rect = col.getBoundingClientRect();
    const startSlot = slotFromClientY(e.clientY, rect.top, grid.num_slots, 2, slotHeight);
    const day = dayForColumn(grid, colIdx);
    onCreateEmpty(day, startSlot, Math.min(startSlot + 2, grid.num_slots));
  }

  function unavailableForColumn(colIdx: number): number[] {
    if (!grid.unavailable_slots) return [];
    const day = dayForColumn(grid, colIdx);
    return grid.unavailable_slots[String(day)] ?? [];
  }

  return (
    <section className="timetable-grid-panel">
      <div className="timetable-grid-scroll">
        <div
          className="timetable-grid"
          style={{
            gridTemplateColumns: colTemplate,
            gridTemplateRows: `${HEADER_HEIGHT}px ${gridHeight}px`,
          }}
        >
          <div className="grid-corner" style={{ gridRow: 1, gridColumn: 1 }} aria-hidden />

          {columnLabels.map((label, colIdx) => (
            <div
              key={`h-${label}-${colIdx}`}
              className="grid-col-header"
              style={{ gridRow: 1, gridColumn: colIdx + 2 }}
            >
              {label}
            </div>
          ))}

          <div
            className="grid-time-gutter"
            style={{ gridRow: 2, gridColumn: 1, height: gridHeight }}
          >
            {Array.from({ length: grid.num_slots }, (_, s) => (
              <div
                key={s}
                className={`grid-time-label${s % 2 === 0 ? " hour" : ""}`}
                style={{ top: s * slotHeight }}
              >
                {s % 2 === 0 ? slotToTimeLabel(s) : ""}
              </div>
            ))}
          </div>

          {columnLabels.map((label, colIdx) => (
            <div
              key={`b-${label}-${colIdx}`}
              className="grid-col-body"
              data-column={colIdx}
              style={{ gridRow: 2, gridColumn: colIdx + 2, height: gridHeight }}
              onDragOver={onColumnDragOver}
              onDrop={(e) => onColumnDrop(e, colIdx)}
              onDoubleClick={(e) => onEmptyDoubleClick(e, colIdx)}
            >
              {Array.from({ length: grid.num_slots }, (_, s) => (
                <div
                  key={s}
                  className={`grid-slot-line${s % 2 === 0 ? " hour" : ""}`}
                  style={{ top: s * slotHeight }}
                />
              ))}

              {unavailableForColumn(colIdx).map((s) => (
                <div
                  key={`u-${s}`}
                  className="grid-unavailable-slot"
                  style={{ top: s * slotHeight, height: slotHeight }}
                />
              ))}

              {byColumn[colIdx].map((b) => {
                const top = b.start_slot * slotHeight + 1;
                const height = (b.end_slot - b.start_slot) * slotHeight - 2;
                const widthPct = 100 / b.lane_depth;
                const leftPct = b.lane * widthPct;
                const meta = cardMeta(b, grid);
                const terms = termBadges(b);
                const locked = b.lock_time || b.lock_staff;
                const showViolation = showAlerts && (b.is_hard || b.is_soft);
                const coTeach = b.sfs_co_teacher_name;
                const fullTitle = cardTitle(b);
                const cardTooltip = [
                  fullTitle,
                  meta,
                  slotRangeLabel(b.start_slot, b.end_slot),
                  showAlerts && b.violations.length
                    ? b.violations.map((v) => v.message).join("\n")
                    : "",
                ]
                  .filter(Boolean)
                  .join("\n");
                return (
                  <div
                    key={b.id}
                    role="button"
                    tabIndex={0}
                    draggable={editable && !b.lock_time}
                    className={[
                      "booking-card",
                      showViolation && b.is_hard ? "violation-hard" : "",
                      showViolation && b.is_soft ? "violation-soft" : "",
                      editable ? "editable" : "",
                      locked ? "locked" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    style={{
                      top,
                      height: Math.max(height, 24),
                      left: `calc(${leftPct}% + 3px)`,
                      width: `calc(${widthPct}% - 6px)`,
                      backgroundColor: b.fill_colour,
                      borderLeftColor: b.border_colour,
                    }}
                    title={cardTooltip}
                    aria-label={fullTitle}
                    onDragStart={(e) => {
                      if (!editable || b.lock_time) return;
                      e.dataTransfer.setData(MIME_BOOKING, String(b.id));
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onDoubleClick={() => editable && onEdit?.(b)}
                    onContextMenu={(e) => {
                      if (!editable) return;
                      e.preventDefault();
                      setContextMenu({ booking: b, x: e.clientX, y: e.clientY });
                    }}
                    onKeyDown={(e) => {
                      if (editable && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault();
                        onEdit?.(b);
                      }
                    }}
                  >
                    <span className="booking-card-time">
                      {slotRangeLabel(b.start_slot, b.end_slot)}
                      {terms && <span className="booking-term-badge">{terms}</span>}
                      {coTeach && <span className="booking-co-badge">+co</span>}
                      {showViolation && b.violations.length > 0 && (
                        <span className="booking-violation-badge" title={b.violations.map((v) => v.message).join("\n")}>
                          !
                        </span>
                      )}
                      {locked && <span className="booking-lock-badge">🔒</span>}
                    </span>
                    <span className="booking-card-title">{cardTitle(b)}</span>
                    {meta && <span className="booking-card-meta">{meta}</span>}
                    {b.notes && <span className="booking-card-notes">{b.notes}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      {contextMenu && editable && (
        <BookingContextMenu
          sessionId={sessionId}
          booking={contextMenu.booking}
          viewKind={viewKind}
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onEdit={() => onEdit?.(contextMenu.booking)}
          onToggleLock={(field) => onToggleLock?.(contextMenu.booking, field)}
          onAlternateMove={(opt) => onAlternateMove?.(contextMenu.booking, opt)}
          onDismissViolation={onDismissViolation}
          onDelete={onDelete ? () => onDelete(contextMenu.booking) : undefined}
        />
      )}
    </section>
  );
}
