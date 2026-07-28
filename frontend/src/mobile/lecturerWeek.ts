/** Build one lecturer's week across every session in a global workspace.
 *
 * A lecturer can teach in several timetable sessions within the same
 * workspace, so their real week is the union of those grids. The aggregated
 * staff endpoint already tells us which sessions they appear in and their
 * staff id in each, so we only fetch the grids that can contain their classes.
 */
import { api, type GlobalAggregatedStaffRow } from "../api";
import type { BookingCard, TimetableGrid } from "../types";

export type LecturerRef = {
  name: string;
  /** One entry per session in the workspace this lecturer appears in. */
  places: { sessionId: number; sessionName: string; staffId: number }[];
};

export type LecturerWeek = {
  name: string;
  days: string[];
  numSlots: number;
  slotMinutes: number;
  firstSlotTime: string;
  weekLabel: string | null;
  /** Bookings from every session, tagged with where they came from. */
  bookings: (BookingCard & { sessionName: string })[];
  /** True when at least one grid came from the offline cache. */
  fromCache: boolean;
  cachedAt: string | null;
};

export function lecturersFromStaffRows(rows: GlobalAggregatedStaffRow[]): LecturerRef[] {
  const out: LecturerRef[] = [];
  for (const row of rows) {
    const places = (row.members ?? [])
      .filter((m) => m.entity_id != null)
      .map((m) => ({
        sessionId: m.session_id,
        sessionName: m.session_name,
        staffId: m.entity_id as number,
      }));
    if (places.length) out.push({ name: row.name, places });
  }
  out.sort((a, b) => a.name.localeCompare(b.name));
  return out;
}

const DEFAULT_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

export async function loadLecturerWeek(ref: LecturerRef): Promise<LecturerWeek> {
  const results = await Promise.all(
    ref.places.map(async (place) => {
      try {
        const grid = await api.timetable(place.sessionId, {
          view: "staff",
          staffId: place.staffId,
          // The viewer never shows warnings, so skip the clash pass entirely.
          clashDetect: "off",
        });
        return { place, grid };
      } catch {
        // One unreachable session must not blank the whole week.
        return { place, grid: null as TimetableGrid | null };
      }
    }),
  );

  const grids = results.filter((r) => r.grid !== null) as {
    place: LecturerRef["places"][number];
    grid: TimetableGrid;
  }[];

  const bookings = grids.flatMap(({ place, grid }) =>
    grid.bookings.map((b) => ({ ...b, sessionName: place.sessionName })),
  );
  bookings.sort((a, b) => a.day - b.day || a.start_slot - b.start_slot);

  const first = grids[0]?.grid;
  const cachedAt = await lastCachedAt();
  return {
    name: ref.name,
    days: first?.days?.length ? first.days : DEFAULT_DAYS,
    numSlots: first?.num_slots ?? 28,
    slotMinutes: first?.slot_minutes ?? 30,
    firstSlotTime: first?.first_slot_time ?? "08:00",
    weekLabel: first?.week_label ?? null,
    bookings,
    fromCache: cachedAt != null && !navigator.onLine,
    cachedAt,
  };
}

/**
 * When the network is down the service worker replays stored grids; read the
 * stamp it wrote so the page can say how old the data is.
 */
async function lastCachedAt(): Promise<string | null> {
  if (!("caches" in window)) return null;
  try {
    const cache = await caches.open("tafetabler-data-v1");
    const keys = await cache.keys();
    let newest: string | null = null;
    for (const key of keys) {
      if (!key.url.includes("/timetable?")) continue;
      const res = await cache.match(key);
      const stamp = res?.headers.get("x-tt-cached-at");
      if (stamp && (newest === null || stamp > newest)) newest = stamp;
    }
    return newest;
  } catch {
    return null;
  }
}

/** Minutes from midnight for a slot index, given the grid's origin time. */
export function slotToMinutes(slot: number, firstSlotTime: string, slotMinutes: number): number {
  const [h, m] = firstSlotTime.split(":").map((n) => Number(n) || 0);
  return h * 60 + m + slot * slotMinutes;
}

export function minutesToLabel(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
