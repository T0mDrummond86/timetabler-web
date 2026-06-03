import { useState } from "react";
import { slotsToDurationLabel } from "../lib/timeUtils";
import { HoldingClass } from "../types";

export const MIME_BOOKING = "application/timetabler-booking";
export const MIME_PENDING = "application/timetabler-pending";

type Props = {
  items: HoldingClass[];
  loading?: boolean;
  acceptBookingDrop?: boolean;
  onBookingDrop?: (bookingId: number) => void;
};

export function HoldingAreaPanel({
  items,
  loading = false,
  acceptBookingDrop = false,
  onBookingDrop,
}: Props) {
  const [dropHover, setDropHover] = useState(false);

  function acceptsDrag(e: React.DragEvent) {
    return acceptBookingDrop && e.dataTransfer.types.includes(MIME_BOOKING);
  }

  function onDragOver(e: React.DragEvent) {
    if (!acceptsDrag(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDropHover(true);
  }

  function onDragLeave(e: React.DragEvent) {
    if (!acceptBookingDrop) return;
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDropHover(false);
  }

  function onDrop(e: React.DragEvent) {
    if (!acceptBookingDrop || !onBookingDrop) return;
    e.preventDefault();
    setDropHover(false);
    const raw = e.dataTransfer.getData(MIME_BOOKING);
    if (!raw) return;
    const bookingId = Number(raw);
    if (Number.isFinite(bookingId)) onBookingDrop(bookingId);
  }

  return (
    <section
      className={`panel holding-panel${dropHover ? " holding-drop-hover" : ""}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div className="panel-header">
        <h2>Holding area</h2>
        <p className="panel-hint">
          Drag classes onto the grid to schedule · drag placecards here to unschedule
        </p>
      </div>

      {loading && !items.length ? (
        <p className="panel-empty">Loading unscheduled classes…</p>
      ) : !items.length ? (
        <p className="panel-empty">
          {acceptBookingDrop
            ? "All classes scheduled — drop a placecard here to return it to holding"
            : "All classes for this course are scheduled."}
        </p>
      ) : (
        <ul className="holding-list">
          {items.map((item) => (
            <li key={`${item.unit_id}-${item.session_part}`}>
              <div
                className="holding-chip"
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(MIME_PENDING, JSON.stringify(item));
                  e.dataTransfer.effectAllowed = "copy";
                }}
              >
                <span className="holding-chip-name">
                  {item.unit_name ?? `Unit #${item.unit_id}`}
                </span>
                <span className="holding-chip-meta">
                  {slotsToDurationLabel(item.duration_slots)}
                  {item.session_part > 1 ? ` · Part ${item.session_part}` : ""}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
