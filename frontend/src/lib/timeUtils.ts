/** Mirror of packages/domain/timetable/constants.py slot grid. */
export const SLOT_MINUTES = 30;
export const NUM_SLOTS = 28;
const FIRST_SLOT_MINUTES = 8 * 60; // 08:00

export function slotToTimeLabel(slot: number): string {
  const total = FIRST_SLOT_MINUTES + slot * SLOT_MINUTES;
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

export function slotRangeLabel(startSlot: number, endSlot: number): string {
  return `${slotToTimeLabel(startSlot)} – ${slotToTimeLabel(endSlot)}`;
}

export function slotsToDurationLabel(slots: number): string {
  const mins = slots * SLOT_MINUTES;
  if (mins % 60 === 0) return `${mins / 60} hr`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h === 0) return `${m} min`;
  return `${h} hr ${m} min`;
}

export function slotOptions(
  numSlots: number,
  firstSlotTime = "08:00",
): { value: number; label: string }[] {
  void firstSlotTime;
  return Array.from({ length: numSlots + 1 }, (_, slot) => ({
    value: slot,
    label: slotToTimeLabel(slot),
  }));
}
