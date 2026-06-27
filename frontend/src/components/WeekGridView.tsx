import { useCallback, useEffect, useRef, useState } from "react";
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
  /** Controlled selection (e.g. lecturer cover left pane). */
  selectedBookingId?: number | null;
  onSelectedBookingChange?: (bookingId: number | null) => void;
  /** Double-click assigns cover instead of opening the edit dialog. */
  coverAssignMode?: boolean;
  onAssignCover?: (booking: BookingCard) => void;
};

function cardTitle(b: BookingCard): string {
  const parts: string[] = [];
  if (b.external_id) parts.push(`[${b.external_id}]`);
  if (b.unit_name) parts.push(b.unit_name);
  return parts.join(" ") || `Booking #${b.id}`;
}

function cardMeta(b: BookingCard, grid: TimetableGrid, includeRoom = true): string {
  const bits: string[] = [];
  const courseViews = ["staff", "room", "day", "unassigned_lecturer"];
  if (courseViews.includes(grid.view) && b.course_code) bits.push(b.course_code);
  if (grid.view !== "staff" && grid.view !== "co_teach" && b.staff_name) {
    bits.push(b.staff_name);
  }
  if (grid.view === "co_teach" && b.staff_name) bits.push(b.staff_name);
  if (includeRoom && grid.view !== "room" && b.room_code) bits.push(b.room_code);
  return bits.join(" · ");
}

function cardRoom(b: BookingCard, grid: TimetableGrid): string | null {
  return grid.view !== "room" && b.room_code ? b.room_code : null;
}

// Approximate rendered line heights (px) used to decide whether a card is tall
// enough to give the room its own line rather than truncating it inline.
const CARD_PAD = 8;
const CARD_GAP = 1;
const CARD_H_TIME = 13;
const CARD_H_TITLE = 16;
const CARD_H_LINE = 15;
const CARD_H_NOTES = 13;

function roomFitsOwnLine(
  cardHeightPx: number,
  hasMetaWithoutRoom: boolean,
  hasNotes: boolean,
): boolean {
  let base = CARD_PAD + CARD_H_TIME + CARD_H_TITLE;
  if (hasMetaWithoutRoom) base += CARD_GAP + CARD_H_LINE;
  if (hasNotes) base += CARD_GAP + CARD_H_NOTES;
  // Require the extra room line to fully fit (+2px safety margin) so it is never clipped.
  return cardHeightPx >= base + CARD_GAP + CARD_H_LINE + 2;
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

function slotIndexFromClientY(
  clientY: number,
  areaTop: number,
  numSlots: number,
  slotHeight: number,
): number {
  const raw = Math.floor((clientY - areaTop) / slotHeight);
  return Math.max(0, Math.min(numSlots - 1, raw));
}

function slotInHighlight(
  slot: number,
  highlight: { start: number; end: number } | null,
): boolean {
  return highlight != null && slot >= highlight.start && slot < highlight.end;
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
  selectedBookingId: selectedBookingIdProp,
  onSelectedBookingChange,
  coverAssignMode = false,
  onAssignCover,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const gutterDragRef = useRef<{ anchor: number; active: boolean } | null>(null);
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
  const [selectedBookingIdInternal, setSelectedBookingIdInternal] = useState<number | null>(null);
  const selectedBookingId = selectedBookingIdProp ?? selectedBookingIdInternal;
  const [slotHighlight, setSlotHighlight] = useState<{ start: number; end: number } | null>(
    null,
  );

  function selectBooking(id: number | null) {
    if (selectedBookingIdProp === undefined) {
      setSelectedBookingIdInternal(id);
    }
    onSelectedBookingChange?.(id);
  }

  useEffect(() => {
    if (
      selectedBookingId != null &&
      !grid.bookings.some((b) => b.id === selectedBookingId)
    ) {
      selectBooking(null);
    }
  }, [grid.bookings, selectedBookingId]);

  useEffect(() => {
    setSlotHighlight((hl) => {
      if (!hl) return null;
      if (hl.start >= grid.num_slots) return null;
      return { start: hl.start, end: Math.min(hl.end, grid.num_slots) };
    });
  }, [grid.num_slots]);

  const zoomScale = zoom / DEFAULT_GRID_ZOOM;
  const slotHeight =
    fit != null
      ? Math.max(6, Math.round(fit.fitSlotHeight * zoomScale))
      : Math.round(BASE_SLOT_HEIGHT * zoom);
  const gridHeight = grid.num_slots * slotHeight;

  const slotIndexFromGutterY = useCallback(
    (clientY: number) => {
      const el = gutterRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      return slotIndexFromClientY(clientY, rect.top, grid.num_slots, slotHeight);
    },
    [grid.num_slots, slotHeight],
  );

  const setHighlightRange = useCallback((anchor: number, current: number) => {
    const start = Math.min(anchor, current);
    const end = Math.max(anchor, current) + 1;
    setSlotHighlight({ start, end });
  }, []);

  useEffect(() => {
    function onWindowMouseMove(e: MouseEvent) {
      const drag = gutterDragRef.current;
      if (!drag?.active) return;
      setHighlightRange(drag.anchor, slotIndexFromGutterY(e.clientY));
    }
    function onWindowMouseUp() {
      if (gutterDragRef.current?.active) {
        gutterDragRef.current.active = false;
      }
    }
    window.addEventListener("mousemove", onWindowMouseMove);
    window.addEventListener("mouseup", onWindowMouseUp);
    return () => {
      window.removeEventListener("mousemove", onWindowMouseMove);
      window.removeEventListener("mouseup", onWindowMouseUp);
    };
  }, [setHighlightRange, slotIndexFromGutterY]);

  function onGutterSlotMouseDown(e: React.MouseEvent, slot: number) {
    e.preventDefault();
    gutterDragRef.current = { anchor: slot, active: true };
    setSlotHighlight({ start: slot, end: slot + 1 });
  }

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

  function tryMoveBookingBySlot(b: BookingCard, delta: -1 | 1) {
    if (!editable || !onMove || b.lock_time) return;
    const duration = b.end_slot - b.start_slot;
    const newStart = b.start_slot + delta;
    if (newStart < 0 || newStart + duration > grid.num_slots) return;
    onMove(b.id, columnIndex(b, grid), newStart);
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
            ref={gutterRef}
            className="grid-time-gutter"
            style={{ gridRow: 2, gridColumn: 1, height: gridHeight }}
          >
            {Array.from({ length: grid.num_slots }, (_, s) => (
              <button
                key={s}
                type="button"
                className={[
                  "grid-time-slot-hit",
                  slotInHighlight(s, slotHighlight) ? "grid-time-slot-hit--active" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{ top: s * slotHeight, height: slotHeight }}
                aria-label={slotToTimeLabel(s)}
                onMouseDown={(e) => onGutterSlotMouseDown(e, s)}
              />
            ))}
            {Array.from({ length: grid.num_slots }, (_, s) => (
              <div
                key={`label-${s}`}
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
              onMouseDown={(e) => {
                if (!(e.target as HTMLElement).closest(".booking-card")) {
                  selectBooking(null);
                }
              }}
            >
              {Array.from({ length: grid.num_slots }, (_, s) => (
                <div
                  key={s}
                  className={`grid-slot-line${s % 2 === 0 ? " hour" : ""}`}
                  style={{ top: s * slotHeight }}
                />
              ))}

              {slotHighlight && (
                <div
                  className="grid-slot-highlight"
                  style={{
                    top: slotHighlight.start * slotHeight,
                    height: (slotHighlight.end - slotHighlight.start) * slotHeight,
                  }}
                />
              )}

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
                const cardHeightPx = Math.max(height, 24);
                const room = cardRoom(b, grid);
                const metaNoRoom = cardMeta(b, grid, false);
                const roomOnOwnLine =
                  room != null && roomFitsOwnLine(cardHeightPx, Boolean(metaNoRoom), Boolean(b.notes));
                const metaDisplay = roomOnOwnLine ? metaNoRoom : meta;
                const terms = termBadges(b);
                const locked = b.lock_time || b.lock_staff;
                const showViolation = showAlerts && (b.is_hard || b.is_soft);
                const isCombined = b.combined_class_group_id != null;
                const coTeach = b.sfs_co_teacher_name;
                const hasCover = Boolean(b.cover_staff_name);
                const selected = selectedBookingId === b.id;
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
                      selected ? "booking-card--selected" : "",
                      hasCover ? "booking-card--cover" : "",
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
                    onClick={() => selectBooking(b.id)}
                    onFocus={() => selectBooking(b.id)}
                    onDoubleClick={() => {
                      if (coverAssignMode && onAssignCover) {
                        onAssignCover(b);
                        return;
                      }
                      if (editable) onEdit?.(b);
                    }}
                    onContextMenu={(e) => {
                      if (!editable) return;
                      e.preventDefault();
                      e.stopPropagation();
                      setContextMenu({ booking: b, x: e.clientX, y: e.clientY });
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowUp") {
                        e.preventDefault();
                        tryMoveBookingBySlot(b, -1);
                        return;
                      }
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        tryMoveBookingBySlot(b, 1);
                        return;
                      }
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
                      {hasCover && (
                        <span className="booking-cover-badge" title={`Cover: ${b.cover_staff_name}`}>
                          cover
                        </span>
                      )}
                      {isCombined && (
                        <span className="booking-combined-badge" title="Combined class (joint cohort delivery)">
                          combined
                        </span>
                      )}
                      {showViolation && b.violations.length > 0 && (
                        <span className="booking-violation-badge" title={b.violations.map((v) => v.message).join("\n")}>
                          !
                        </span>
                      )}
                      {locked && <span className="booking-lock-badge">🔒</span>}
                    </span>
                    <span className="booking-card-title">{cardTitle(b)}</span>
                    {metaDisplay && <span className="booking-card-meta">{metaDisplay}</span>}
                    {roomOnOwnLine && room && (
                      <span className="booking-card-room">{room}</span>
                    )}
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
