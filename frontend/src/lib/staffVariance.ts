/** Variance categories and UI labels (desktop StaffEditor parity). */

export type StaffVarianceCategory =
  | "on_target"
  | "full_fte_overtime"
  | "full_fte_shortfall"
  | "part_fte_variation"
  | "part_fte_variation_overtime"
  | "unknown";

export const VARIANCE_FILTER_OPTIONS: { label: string; value: "all" | StaffVarianceCategory }[] = [
  { label: "All lecturers", value: "all" },
  { label: "On target", value: "on_target" },
  { label: "Overtime (1 FTE)", value: "full_fte_overtime" },
  { label: "Hours shortfall (1 FTE)", value: "full_fte_shortfall" },
  { label: "Variation to hours (< 1 FTE, under 21h)", value: "part_fte_variation" },
  { label: "Variation + overtime (< 1 FTE, over 21h)", value: "part_fte_variation_overtime" },
  { label: "Incomplete data", value: "unknown" },
];

export function varianceCellClass(category: string): string {
  switch (category) {
    case "full_fte_overtime":
      return "variance-cell variance-full-fte-overtime";
    case "full_fte_shortfall":
      return "variance-cell variance-full-fte-shortfall";
    case "part_fte_variation":
      return "variance-cell variance-part-fte-variation";
    case "part_fte_variation_overtime":
      return "variance-cell variance-part-fte-variation-overtime";
    case "unknown":
      return "variance-cell variance-unknown";
    default:
      return "variance-cell";
  }
}

export function varianceTooltip(category: string): string {
  switch (category) {
    case "on_target":
      return "Total workload minus lecturing hours (FTE × 21).";
    case "unknown":
      return "Set FTE to classify variance.";
    case "full_fte_overtime":
      return "Overtime: total workload is above the lecturing allocation.";
    case "full_fte_shortfall":
      return "Hours shortfall: total workload is below the lecturing allocation.";
    case "part_fte_variation":
      return "Variation to hours required: workload differs from allocation and total is under one FTE (21h).";
    case "part_fte_variation_overtime":
      return "Variation and overtime: workload differs from allocation and total exceeds one FTE (21h).";
    default:
      return "Total workload minus lecturing hours (FTE × 21).";
  }
}

export function formatHours(v: number | null | undefined, decimals = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(decimals);
}

export function formatOptionalNum(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "";
  return String(v);
}
