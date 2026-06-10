import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AlternatePlacementOption, AlternateSlots, BookingCard } from "../types";
import type { ViewKind } from "../viewKinds";

type Props = {
  sessionId: number;
  booking: BookingCard;
  viewKind: ViewKind;
  x: number;
  y: number;
  onClose: () => void;
  onEdit: () => void;
  onToggleLock: (field: "lock_time" | "lock_staff") => void;
  onAlternateMove: (option: AlternatePlacementOption) => void;
  onDismissViolation?: (bookingId: number, code: string) => void;
};

export function BookingContextMenu({
  sessionId,
  booking,
  viewKind,
  x,
  y,
  onClose,
  onEdit,
  onToggleLock,
  onAlternateMove,
  onDismissViolation,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [slots, setSlots] = useState<AlternateSlots | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedDay, setExpandedDay] = useState<number | null>(null);

  const showAlternate =
    viewKind === "course" ||
    viewKind === "course_semester" ||
    viewKind === "staff" ||
    viewKind === "room" ||
    viewKind === "block_delivery";
  const timesOnly = viewKind === "staff";

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    if (!showAlternate) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await api.alternateSlots(sessionId, booking.id, { timesOnly });
        if (!cancelled) setSlots(data);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, booking.id, showAlternate, timesOnly]);

  return (
    <div
      ref={ref}
      className="booking-context-menu"
      style={{ top: y, left: x }}
      role="menu"
    >
      <button type="button" className="ctx-item" onClick={() => { onEdit(); onClose(); }}>
        Edit booking…
      </button>
      {booking.violations.length > 0 && onDismissViolation && (
        <>
          <div className="ctx-divider" />
          <span className="ctx-label">Dismiss warning</span>
          {booking.violations.map((v) => (
            <button
              key={v.code}
              type="button"
              className="ctx-item"
              onClick={() => {
                onDismissViolation(booking.id, v.code);
                onClose();
              }}
            >
              {v.code}
            </button>
          ))}
        </>
      )}
      {slots && slots.available_rooms.length > 0 && (
        <>
          <div className="ctx-divider" />
          <span className="ctx-label">Available rooms</span>
          {slots.available_rooms.map((r) => (
            <button
              key={r.room_id}
              type="button"
              className="ctx-item"
              disabled={r.is_current}
              onClick={() => {
                onAlternateMove({
                  day: booking.day,
                  start_slot: booking.start_slot,
                  end_slot: booking.end_slot,
                  time_label: "",
                  room_id: r.room_id,
                  room_code: r.room_code,
                  staff_id: null,
                  is_current: r.is_current,
                });
                onClose();
              }}
            >
              {r.room_code}
              {r.is_current ? " ◆" : ""}
            </button>
          ))}
        </>
      )}
      {showAlternate && (
        <>
          <div className="ctx-divider" />
          <span className="ctx-label">Move to alternate slot</span>
          {loading && <span className="ctx-muted">Loading…</span>}
          {!loading && slots && !slots.days.length && (
            <span className="ctx-muted">No open slots</span>
          )}
          {slots?.days.map((day) => (
            <div key={day.day} className="ctx-submenu">
              <button
                type="button"
                className="ctx-item ctx-expand"
                onClick={() => setExpandedDay(expandedDay === day.day ? null : day.day)}
              >
                {day.day_label}
                {day.is_current_day ? " ◆" : ""}
              </button>
              {expandedDay === day.day &&
                day.slots.map((slot) =>
                  slot.options.map((opt) => (
                    <button
                      key={`${opt.day}-${opt.start_slot}-${opt.room_id}`}
                      type="button"
                      className="ctx-item ctx-nested"
                      disabled={opt.is_current}
                      onClick={() => {
                        onAlternateMove(opt);
                        onClose();
                      }}
                    >
                      {slot.time_label} — {opt.room_code}
                      {opt.is_current ? " ◆" : ""}
                    </button>
                  )),
                )}
            </div>
          ))}
        </>
      )}
      <div className="ctx-divider" />
      <button type="button" className="ctx-item" onClick={() => { onToggleLock("lock_time"); onClose(); }}>
        {booking.lock_time ? "Unlock time" : "Lock time"}
      </button>
      <button type="button" className="ctx-item" onClick={() => { onToggleLock("lock_staff"); onClose(); }}>
        {booking.lock_staff ? "Unlock lecturer" : "Lock lecturer"}
      </button>
    </div>
  );
}
