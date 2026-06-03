/** Internal scale at which the UI shows 100% (matches desktop compact default). */
export const GRID_ZOOM_BASE = 0.5;

export const GRID_ZOOM_MIN = 0.25;
export const GRID_ZOOM_MAX = 2;
export const GRID_ZOOM_STEP = 0.1;

export const DEFAULT_GRID_ZOOM = GRID_ZOOM_BASE;

export function displayZoomPercent(internal: number): number {
  return Math.round((internal / GRID_ZOOM_BASE) * 100);
}

export function internalFromDisplayPercent(display: number): number {
  const internal = (display / 100) * GRID_ZOOM_BASE;
  return Math.round(Math.max(GRID_ZOOM_MIN, Math.min(GRID_ZOOM_MAX, internal)) * 10) / 10;
}

/** Parse `?zoom=` — new URLs use display % (100 = default); legacy used internal × 100. */
export function parseZoomUrlParam(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_GRID_ZOOM;
  const n = Number(raw);
  if (!Number.isFinite(n)) return DEFAULT_GRID_ZOOM;
  if (n >= 100) return internalFromDisplayPercent(n);
  return Math.max(GRID_ZOOM_MIN, Math.min(GRID_ZOOM_MAX, Math.round((n / 100) * 10) / 10));
}

export function clampGridZoom(internal: number): number {
  return Math.round(Math.max(GRID_ZOOM_MIN, Math.min(GRID_ZOOM_MAX, internal)) * 10) / 10;
}

export function zoomIn(internal: number): number {
  return clampGridZoom(internal + GRID_ZOOM_STEP);
}

export function zoomOut(internal: number): number {
  return clampGridZoom(internal - GRID_ZOOM_STEP);
}

export function resetGridZoom(): number {
  return DEFAULT_GRID_ZOOM;
}
