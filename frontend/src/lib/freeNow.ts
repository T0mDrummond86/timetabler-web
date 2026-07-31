/** Who is free at this moment, across the timetables the viewer has selected.
 *
 * "On campus" is inferred from the timetable rather than from any presence
 * signal: a lecturer teaching at some point today is presumed to be on site,
 * so a gap in their day is someone you could actually walk up to. A lecturer
 * with nothing scheduled today is presumed not to be in at all.
 *
 * One ``view=day`` grid per session returns every booking for that day, so
 * this costs one request per selected session rather than one per lecturer.
 */
import { api } from "../api";
import type { BookingCard } from "../types";

export type FreeState = "busy" | "free_on_campus" | "free_off_campus";

export type FreeRow = {
  name: string;
  state: FreeState;
  /** The class they are in right now (busy only). */
  current?: { label: string; room: string | null; until: string };
  /** Their next class today, if any — what they are free until. */
  next?: { label: string; room: string | null; from: string };
  /** Classes they have today, for context. */
  countToday: number;
};

export type FreeNowResult = {
  /** Slot the clock currently falls in, or null when outside the grid. */
  slot: number | null;
  dayIndex: number;
  dayLabel: string;
  /** True at the weekend or outside the timetabled day. */
  offGrid: boolean;
  clockLabel: string;
  rows: FreeRow[];
};

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const SLOT_MINUTES = 30;
const FIRST_SLOT_MINUTES = 8 * 60;
const NUM_SLOTS = 28;

function label(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function slotStart(slot: number): string {
  return label(FIRST_SLOT_MINUTES + slot * SLOT_MINUTES);
}

/** Grid day index for a JS Date, or null at the weekend. */
export function gridDayFor(now: Date): number | null {
  const js = now.getDay(); // 0 = Sunday
  if (js === 0 || js === 6) return null;
  return js - 1;
}

/** Slot containing this moment, or null before/after the timetabled day. */
export function slotFor(now: Date): number | null {
  const mins = now.getHours() * 60 + now.getMinutes();
  const slot = Math.floor((mins - FIRST_SLOT_MINUTES) / SLOT_MINUTES);
  return slot >= 0 && slot < NUM_SLOTS ? slot : null;
}

function cardLabel(b: BookingCard): string {
  return b.unit_name ?? b.course_code ?? "Class";
}

export async function loadFreeNow(
  sessionIds: number[],
  allLecturerNames: string[],
  now: Date = new Date(),
): Promise<FreeNowResult> {
  const dayIndex = gridDayFor(now);
  const slot = slotFor(now);
  const clockLabel = label(now.getHours() * 60 + now.getMinutes());

  if (dayIndex === null) {
    return {
      slot: null,
      dayIndex: -1,
      dayLabel: now.toLocaleDateString(undefined, { weekday: "long" }),
      offGrid: true,
      clockLabel,
      rows: [],
    };
  }

  const grids = await Promise.all(
    sessionIds.map(async (id) => {
      try {
        return await api.timetable(id, { view: "day", day: dayIndex, clashDetect: "off" });
      } catch {
        // One unreachable session must not blank the whole answer.
        return null;
      }
    }),
  );

  // Every booking today, grouped by lecturer name.
  const byLecturer = new Map<string, BookingCard[]>();
  for (const grid of grids) {
    if (!grid) continue;
    for (const b of grid.bookings) {
      if (b.day !== dayIndex) continue;
      const who = b.staff_name;
      if (!who) continue;
      const list = byLecturer.get(who);
      if (list) list.push(b);
      else byLecturer.set(who, [b]);
    }
  }

  const rows: FreeRow[] = [];
  for (const name of allLecturerNames) {
    const today = (byLecturer.get(name) ?? []).sort((a, b) => a.start_slot - b.start_slot);
    if (!today.length) {
      rows.push({ name, state: "free_off_campus", countToday: 0 });
      continue;
    }
    // Outside the timetabled day nobody is mid-class, but they were in today.
    const inClass =
      slot === null ? undefined : today.find((b) => b.start_slot <= slot && slot < b.end_slot);
    const upcoming =
      slot === null ? undefined : today.find((b) => b.start_slot > slot);

    if (inClass) {
      rows.push({
        name,
        state: "busy",
        countToday: today.length,
        current: {
          label: cardLabel(inClass),
          room: inClass.room_code ?? null,
          until: slotStart(inClass.end_slot),
        },
      });
    } else {
      rows.push({
        name,
        state: "free_on_campus",
        countToday: today.length,
        next: upcoming
          ? {
              label: cardLabel(upcoming),
              room: upcoming.room_code ?? null,
              from: slotStart(upcoming.start_slot),
            }
          : undefined,
      });
    }
  }

  rows.sort((a, b) => a.name.localeCompare(b.name));
  return {
    slot,
    dayIndex,
    dayLabel: DAY_LABELS[dayIndex] ?? "Today",
    offGrid: slot === null,
    clockLabel,
    rows,
  };
}
