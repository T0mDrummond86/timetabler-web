/** Card-friendly fills aligned with the desktop screen colour palette. */
export const CLASS_COLOUR_PRESETS = [
  "#B8D4F0",
  "#F5C4C8",
  "#B8E6B8",
  "#F5EEB8",
  "#E0C4E8",
  "#B8E8F5",
  "#F5D4B8",
  "#C4D8F5",
  "#F5C4E0",
  "#D0E8B8",
  "#F5E0A8",
  "#C8C8F0",
  "#B8E8D8",
  "#F0B8B8",
  "#E0E0A8",
  "#B0C0E8",
] as const;

export function normalizeHexColour(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  const hex = s.startsWith("#") ? s : `#${s}`;
  return /^#[0-9A-Fa-f]{6}$/.test(hex) ? hex.toUpperCase() : null;
}
