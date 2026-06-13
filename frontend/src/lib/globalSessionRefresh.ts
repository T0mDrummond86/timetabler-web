/** Track when linked timetable sessions changed — global views refresh on exit or manual update. */

const STORAGE_KEY = "timetabler-global-dirty-ids";

export const GLOBAL_DIRTY_STORAGE_KEY = STORAGE_KEY;

function readDirtyIds(): Set<number> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is number => typeof id === "number" && id > 0));
  } catch {
    return new Set();
  }
}

function writeDirtyIds(ids: Set<number>): void {
  try {
    if (ids.size === 0) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    /* private mode / quota */
  }
}

/** Call when leaving a timetable session that belongs to a global group. */
export function markGlobalSessionDirty(globalSessionId: number): void {
  if (!globalSessionId) return;
  const ids = readDirtyIds();
  ids.add(globalSessionId);
  writeDirtyIds(ids);
}

export function isGlobalSessionDirty(globalSessionId: number): boolean {
  if (!globalSessionId) return false;
  return readDirtyIds().has(globalSessionId);
}

export function clearGlobalSessionDirty(globalSessionId: number): void {
  if (!globalSessionId) return;
  const ids = readDirtyIds();
  ids.delete(globalSessionId);
  writeDirtyIds(ids);
}
