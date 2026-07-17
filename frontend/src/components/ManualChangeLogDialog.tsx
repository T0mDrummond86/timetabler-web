/** Pick which fields of a placecard to record as a manual change-log entry. */
import { useState } from "react";
import type { ManualChangeField } from "../api";
import type { BookingCard } from "../types";
import { slotRangeLabel } from "../lib/timeUtils";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

type Props = {
  booking: BookingCard;
  saving: boolean;
  onClose: () => void;
  onConfirm: (fields: ManualChangeField[]) => void;
};

export function ManualChangeLogDialog({ booking, saving, onClose, onConfirm }: Props) {
  const [checked, setChecked] = useState<Set<ManualChangeField>>(new Set());

  const options: { field: ManualChangeField; label: string; value: string }[] = [
    { field: "lecturer", label: "Lecturer", value: booking.staff_name ?? "—" },
    {
      field: "time",
      label: "Time",
      value: slotRangeLabel(booking.start_slot, booking.end_slot),
    },
    { field: "day", label: "Day", value: DAY_NAMES[booking.day] ?? `Day ${booking.day + 1}` },
    { field: "room", label: "Room", value: booking.room_code ?? "—" },
  ];

  function toggle(field: ManualChangeField) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal card manual-change-modal"
        role="dialog"
        aria-labelledby="manual-change-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2 id="manual-change-title">Log manual change</h2>
            <p className="modal-lead">{booking.unit_name ?? `Booking #${booking.id}`}</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <p className="muted entity-hint">
          Which field(s) changed? The record lands on the resolved change log and the
          admin export highlights exactly these fields.
        </p>

        <div className="manual-change-options">
          {options.map((opt) => (
            <label key={opt.field} className="checkbox manual-change-option">
              <input
                type="checkbox"
                checked={checked.has(opt.field)}
                onChange={() => toggle(opt.field)}
              />
              <span className="manual-change-label">{opt.label}</span>
              <span className="muted">{opt.value}</span>
            </label>
          ))}
        </div>

        <footer className="modal-footer">
          <span className="modal-footer-spacer" />
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={saving || checked.size === 0}
            onClick={() => onConfirm([...checked])}
          >
            {saving ? "Logging…" : "Log change"}
          </button>
        </footer>
      </div>
    </div>
  );
}
