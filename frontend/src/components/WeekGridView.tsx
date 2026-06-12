import { useRef, useState } from "react";
import { useGridFitMetrics } from "../hooks/useGridFitMetrics";
import { slotRangeLabel, slotToTimeLabel } from "../lib/timeUtils";
import { BookingCard, HoldingClass, TimetableGrid } from "../types";
import type { AlternatePlacementOption } from "../types";
import type { ViewKind } from "../viewKinds";
import { BookingContextMenu } from "./BookingContextMenu";
import { ClassColourDialog } from "./ClassColourDialog";
import { MIME_BOOKING, MIME_PENDING } from "./HoldingAreaPanel";
import { DEFAULT_GRID_ZOOM } from "../lib/gridZoom";

export const BASE_SLOT_HEIGHT = 28;
export const GRID_HEADER_HEIGHT = 40;
const HEADER_HEIGHT = GRID_HEADER_HEIGHT;
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
  onSetClassColour?: (unitId: number, fill: string | null) => void;
  colourByClass?: boolean;
  /** Stretch rows to fill the grid area (full day visible, no dead space). */
  fitToViewport?: boolean;
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
  const t1 = Boolean(b.in_term_1);
  const t2 = Boolean(b.in_term_2);
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
  onSetClassColour,
  colourByClass = true,
  fitToViewport = false,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const fit = useGridFitMetrics(scrollRef, grid.num_slots, HEADER_HEIGHT, fitToViewport);
  const [contextMenu, setContextMenu] = useState<{
    booking: BookingCard;
    x: number;
    y: number;
  } | null>(null);
  const [classColourTarget, setClassColourTarget] = useState<{
    unitId: number;
    className: string | null;
    currentFill: string | null;
  } | null>(null);
  const zoomScale = zoom / DEFAULT_GRID_ZOOM;
  const slotHeight =
    fit != null
      ? Math.max(6, Math.round(fit.fitSlotHeight * zoomScale))
      : Math.round(BASE_SLOT_HEIGHT * zoom);
  const gridHeight = grid.num_slots * slotHeight;
  const needsScroll =
    fit != null
      ? HEADER_HEIGHT + gridHeight > fit.containerHeight + 1
      : zoom > DEFAULT_GRID_ZOOM;
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

  function linkedBusyForColumn(colIdx: number): number[] {
    if (!grid.linked_session_busy_slots) return [];
    const day = dayForColumn(grid, colIdx);
    const busy = new Set(grid.linked_session_busy_slots[String(day)] ?? []);
    const blocked = new Set(unavailableForColumn(colIdx));
    return [...busy].filter((s) => !blocked.has(s));
  }

  return (
    <section className={`timetable-grid-panel${fitToViewport ? " timetable-grid-panel--fit" : ""}`}>
      <div
        ref={scrollRef}
        className={[
          "timetable-grid-scroll",
          fitToViewport ? "timetable-grid-scroll--fit" : "",
          needsScroll ? "timetable-grid-scroll--overflow" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <div
          className="timetable-grid"
          style={{
            gridTemplateColumns: colTemplate,
            gridTemplateRows: `${HEADER_HEIGHT}px ${gridHeight}px`,
            ["--slot-h" as string]: `${slotHeight}px`,
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

              {linkedBusyForColumn(colIdx).map((s) => (
                <div
                  key={`l-${s}`}
                  className="grid-linked-busy-slot"
                  title={
                    grid.linked_session_busy_label
                      ? `Scheduled in linked session: ${grid.linked_session_busy_label}`
                      : "Scheduled in a linked session"
                  }
                  style={{ top: s * slotHeight, height: slotHeight }}
                />
              ))}

              {byColumn[colIdx].some(
                (b) => Boolean(b.in_term_1) !== Boolean(b.in_term_2),
              ) && <div className="grid-term-divider" aria-hidden />}

              {byColumn[colIdx].map((b) => {
                const top = b.start_slot * slotHeight + 1;
                const height = (b.end_slot - b.start_slot) * slotHeight - 2;
                const widthPct = b.layout_width_pct ?? 100 / b.lane_depth;
                const leftPct = b.layout_left_pct ?? b.lane * (100 / b.lane_depth);
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
                      e.stopPropagation();
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
          onPickClassColour={
            onSetClassColour && contextMenu.booking.unit_id != null
              ? () =>
                  setClassColourTarget({
                    unitId: contextMenu.booking.unit_id!,
                    className: contextMenu.booking.unit_name,
                    currentFill: contextMenu.booking.unit_screen_fill_colour ?? null,
                  })
              : undefined
          }
          colourByClass={colourByClass}
        />
      )}
      {classColourTarget && onSetClassColour && (
        <ClassColourDialog
          className={classColourTarget.className}
          currentFill={classColourTarget.currentFill}
          onApply={(fill) => {
            onSetClassColour(classColourTarget.unitId, fill);
            setClassColourTarget(null);
          }}
          onReset={
            classColourTarget.currentFill
              ? () => {
                  onSetClassColour(classColourTarget.unitId, null);
                  setClassColourTarget(null);
                }
              : undefined
          }
          onClose={() => setClassColourTarget(null)}
        />
      )}
    </section>
  );
}
