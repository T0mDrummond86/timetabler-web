import { FormEvent, useEffect, useMemo, useState } from "react";
import { Room, Staff, Unit } from "../api";
import { slotOptions, slotRangeLabel } from "../lib/timeUtils";
import { TimetableGrid } from "../types";

type Props = {
  grid: TimetableGrid;
  courseId: number;
  day: number;
  startSlot: number;
  endSlot: number;
  units: Unit[];
  staff: Staff[];
  rooms: Room[];
  saving: boolean;
  onClose: () => void;
  onCreate: (body: {
    unit_id: number;
    day: number;
    start_slot: number;
    end_slot: number;
    staff_id?: number | null;
    room_id?: number | null;
    notes?: string | null;
  }) => void;
};

export function BookingCreateDialog({
  grid,
  courseId,
  day,
  startSlot,
  endSlot,
  units,
  staff,
  rooms,
  saving,
  onClose,
  onCreate,
}: Props) {
  const [unitId, setUnitId] = useState<number | "">(units[0]?.id ?? "");
  const [staffId, setStaffId] = useState<number | "">("");
  const [roomId, setRoomId] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [slotStart, setSlotStart] = useState(startSlot);
  const [slotEnd, setSlotEnd] = useState(endSlot);
  const [slotDay, setSlotDay] = useState(day);

  const startOptions = useMemo(() => slotOptions(grid.num_slots - 1), [grid.num_slots]);
  const endOptions = useMemo(
    () => slotOptions(grid.num_slots).filter((o) => o.value > slotStart),
    [grid.num_slots, slotStart],
  );

  useEffect(() => {
    setSlotDay(day);
    setSlotStart(startSlot);
    setSlotEnd(endSlot);
  }, [day, startSlot, endSlot]);

  useEffect(() => {
    if (slotEnd <= slotStart) setSlotEnd(Math.min(slotStart + 2, grid.num_slots));
  }, [slotStart, slotEnd, grid.num_slots]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (unitId === "") return;
    onCreate({
      unit_id: unitId,
      day: slotDay,
      start_slot: slotStart,
      end_slot: slotEnd,
      staff_id: staffId === "" ? null : staffId,
      room_id: roomId === "" ? null : roomId,
      notes: notes.trim() || null,
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal dialog" role="dialog" aria-modal onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>New booking</h2>
          <button type="button" className="btn-secondary btn-xs" onClick={onClose}>
            Close
          </button>
        </div>
        <form className="modal-form" onSubmit={submit}>
          <p className="muted">
            {grid.days[slotDay] ?? `Day ${slotDay}`} · {slotRangeLabel(slotStart, slotEnd)} · course #{courseId}
          </p>
          <label>
            Class
            <select value={unitId} required onChange={(e) => setUnitId(Number(e.target.value))}>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Day
            <select value={slotDay} onChange={(e) => setSlotDay(Number(e.target.value))}>
              {grid.days.map((d, i) => (
                <option key={d} value={i}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <div className="row gap">
            <label>
              Start
              <select value={slotStart} onChange={(e) => setSlotStart(Number(e.target.value))}>
                {startOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              End
              <select value={slotEnd} onChange={(e) => setSlotEnd(Number(e.target.value))}>
                {endOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Lecturer
            <select value={staffId} onChange={(e) => setStaffId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">—</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Room
            <select value={roomId} onChange={(e) => setRoomId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">—</option>
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.code}
                </option>
              ))}
            </select>
          </label>
          <label>
            Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </label>
          <div className="row gap">
            <button type="submit" className="btn-primary" disabled={saving || unitId === ""}>
              {saving ? "Creating…" : "Create booking"}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
