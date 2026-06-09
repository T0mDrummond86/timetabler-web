/** Non-negative integer string for plain numeric text fields (no spinner buttons). */
export function sanitizeNonNegIntInput(raw: string): string {
  return raw.replace(/\D/g, "");
}

export function nonNegIntFromInput(raw: string, fallback = 0): number {
  const s = sanitizeNonNegIntInput(raw);
  if (!s) return fallback;
  const n = Number(s);
  return Number.isFinite(n) ? n : fallback;
}
