const STORAGE_KEY = "timetabler-recent-sessions";

export function readRecentSessionIds(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is number => typeof id === "number" && Number.isFinite(id));
  } catch {
    return [];
  }
}

export function recordSessionOpen(sessionId: number): void {
  const next = [sessionId, ...readRecentSessionIds().filter((id) => id !== sessionId)].slice(0, 30);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

export function recentRank(sessionId: number, recentIds: number[]): number {
  const index = recentIds.indexOf(sessionId);
  return index === -1 ? Number.MAX_SAFE_INTEGER : index;
}
