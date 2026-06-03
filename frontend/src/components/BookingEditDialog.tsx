import { FormEvent, useEffect, useMemo, useState } from "react";
import { Room, Staff } from "../api";
import { slotOptions, slotRangeLabel } from "../lib/timeUtils";
import { BookingCard, TimetableGrid } from "../types";

type Props = {
  booking: BookingCard;
  grid: TimetableGrid;
  staff: Staff[];
  rooms: Room[];
  saving: boolean;
  onClose: () => void;
  onSave: (patch: {
    day?: number;
    start_slot?: number;
    end_slot?: number;
    notes?: string | null;
    staff_id?: number | null;
    room_id?: number | null;
    external_id?: string | null;
    in_term_1?: number;
    in_term_2?: number;
    sfs_co_teacher_staff_id?: number | null;
    sfs_co_teacher_in_term_1?: number;
    sfs_co_teacher_in_term_2?: number;
    online_student_count?: number | null;
  }) => void;
  onDelete?: () => void;
};

export function BookingEditDialog({
  booking,
  grid,
  staff,
  rooms,
  saving,
  onClose,
  onSave,
  onDelete,
}: Props) {
  const [day, setDay] = useState(booking.day);
  const [startSlot, setStartSlot] = useState(booking.start_slot);
  const [endSlot, setEndSlot] = useState(booking.end_slot);
  const [notes, setNotes] = useState(booking.notes ?? "");
  const [externalId, setExternalId] = useState(booking.external_id ?? "");
  const [inTerm1, setInTerm1] = useState(booking.in_term_1 !== false);
  const [inTerm2, setInTerm2] = useState(booking.in_term_2 !== false);
  const [staffId, setStaffId] = useState<number | "">(
    staff.find((s) => s.name === booking.staff_name)?.id ?? "",
  );
  const [roomId, setRoomId] = useState<number | "">(
    rooms.find((r) => r.code === booking.room_code)?.id ?? "",
  );
  const [coStaffId, setCoStaffId] = useState<number | "">(booking.sfs_co_teacher_staff_id ?? "");
  const [coTerm1, setCoTerm1] = useState(booking.sfs_co_teacher_in_term_1 ?? false);
  const [coTerm2, setCoTerm2] = useState(booking.sfs_co_teacher_in_term_2 ?? false);
  const [onlineStudents, setOnlineStudents] = useState<string>(
    booking.online_student_count != null ? String(booking.online_student_count) : "",
  );

  const selectedRoom = rooms.find((r) => r.id === (roomId === "" ? null : roomId));
  const roomOnline =
    booking.room_is_online ||
    Boolean(selectedRoom?.room_type?.toLowerCase().includes("online")) ||
    Boolean(selectedRoom?.code?.toLowerCase().includes("online"));

  const startOptions = useMemo(() => slotOptions(grid.num_slots - 1), [grid.num_slots]);
  const endOptions = useMemo(
    () => slotOptions(grid.num_slots).filter((o) => o.value > startSlot),
    [grid.num_slots, startSlot],
  );

  useEffect(() => {
    setDay(booking.day);
    setStartSlot(booking.start_slot);
    setEndSlot(booking.end_slot);
    setNotes(booking.notes ?? "");
    setExternalId(booking.external_id ?? "");
    setInTerm1(booking.in_term_1 !== false);
    setInTerm2(booking.in_term_2 !== false);
    setStaffId(staff.find((s) => s.name === booking.staff_name)?.id ?? "");
    setRoomId(rooms.find((r) => r.code === booking.room_code)?.id ?? "");
    setCoStaffId(booking.sfs_co_teacher_staff_id ?? "");
    setCoTerm1(booking.sfs_co_teacher_in_term_1 ?? false);
    setCoTerm2(booking.sfs_co_teacher_in_term_2 ?? false);
    setOnlineStudents(
      booking.online_student_count != null ? String(booking.online_student_count) : "",
    );
  }, [booking, staff, rooms]);

  useEffect(() => {
    if (endSlot <= startSlot) {
      setEndSlot(Math.min(startSlot + 1, grid.num_slots));
    }
  }, [startSlot, endSlot, grid.num_slots]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!inTerm1 && !inTerm2) return;
    onSave({
      day,
      start_slot: startSlot,
      end_slot: endSlot,
      notes: notes.trim() || null,
      staff_id: staffId === "" ? null : staffId,
      room_id: roomId === "" ? null : roomId,
      external_id: externalId.trim() || null,
      in_term_1: inTerm1 ? 1 : 0,
      in_term_2: inTerm2 ? 1 : 0,
      sfs_co_teacher_staff_id: coStaffId === "" ? null : coStaffId,
      sfs_co_teacher_in_term_1: coTerm1 ? 1 : 0,
      sfs_co_teacher_in_term_2: coTerm2 ? 1 : 0,
      online_student_count:
        roomOnline && onlineStudents.trim() ? Number(onlineStudents) : null,
    });
  }

  const timePreview = slotRangeLabel(startSlot, endSlot);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal card booking-edit-modal"
        role="dialog"
        aria-labelledby="edit-booking-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2 id="edit-booking-title">Edit booking</h2>
            <p className="modal-lead">
              {booking.unit_name ?? `Booking #${booking.id}`}
              {booking.session_part && booking.session_part > 1 ? ` · Part ${booking.session_part}` : ""}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <form className="form modal-form" onSubmit={submit}>
          <label>
            ID tag
            <input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="Optional card ID" />
          </label>

          <fieldset className="qual-link-fieldset">
            <legend>Teaching weeks</legend>
            <p className="muted entity-hint">
              Choose which semester terms this booking counts toward. At least one must be selected.
            </p>
            <div className="form-row-2 term-row">
              <label className="checkbox">
                <input type="checkbox" checked={inTerm1} onChange={(e) => setInTerm1(e.target.checked)} />
                Term 1
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={inTerm2} onChange={(e) => setInTerm2(e.target.checked)} />
                Term 2
              </label>
            </div>
          </fieldset>

          <label>
            Day
            <select value={day} onChange={(e) => setDay(Number(e.target.value))}>
              {grid.days.map((name, i) => (
                <option key={name} value={i}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <div className="form-row-2">
            <label>
              Start time
              <select value={startSlot} onChange={(e) => setStartSlot(Number(e.target.value))}>
                {startOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              End time
              <select value={endSlot} onChange={(e) => setEndSlot(Number(e.target.value))}>
                {endOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="time-preview-hint muted" aria-live="polite">
            Scheduled: {timePreview}
          </p>

          <label>
            Lecturer
            <select
              value={staffId}
              onChange={(e) => setStaffId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">Unassigned</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            SFS co-teacher
            <select
              value={coStaffId}
              onChange={(e) => setCoStaffId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">None</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>

          {coStaffId !== "" && (
            <div className="form-row-2 term-row">
              <label className="checkbox">
                <input type="checkbox" checked={coTerm1} onChange={(e) => setCoTerm1(e.target.checked)} />
                Co-teach T1
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={coTerm2} onChange={(e) => setCoTerm2(e.target.checked)} />
                Co-teach T2
              </label>
            </div>
          )}

          <label>
            Room
            <select
              value={roomId}
              onChange={(e) => setRoomId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">Unassigned</option>
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.code}
                  {r.name ? ` — ${r.name}` : ""}
                </option>
              ))}
            </select>
          </label>

          {roomOnline && (
            <label>
              Online students
              <input
                type="number"
                min={0}
                value={onlineStudents}
                onChange={(e) => setOnlineStudents(e.target.value)}
                placeholder="Default 20"
              />
            </label>
          )}

          <label>
            Notes
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>

          <footer className="modal-footer">
            {onDelete && (
              <button type="button" className="btn-danger" onClick={onDelete} disabled={saving}>
                Delete
              </button>
            )}
            <span className="modal-footer-spacer" />
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving || (!inTerm1 && !inTerm2)}>
              {saving ? "Saving…" : "Save changes"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
