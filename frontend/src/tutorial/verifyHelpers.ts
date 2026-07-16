/** Read-only backend checks shared by tutorial step verifies. */
import { api } from "../api";
import type { VerifyCtx } from "./types";

/** True when the (filtered) violations report has a row of this code. */
export async function hasViolation(
  ctx: VerifyCtx,
  code: string,
  opts: { lecturer?: string; severity?: "hard" | "soft" } = {},
): Promise<boolean> {
  const report = await api.violationsReport(ctx.sessionId, opts.severity);
  return report.rows.some(
    (row) =>
      row.type === code &&
      (!opts.lecturer || (row.lecturer ?? "").includes(opts.lecturer)),
  );
}

export async function noViolation(
  ctx: VerifyCtx,
  code: string,
  opts: { lecturer?: string; severity?: "hard" | "soft" } = {},
): Promise<boolean> {
  return !(await hasViolation(ctx, code, opts));
}

/** Unit names currently unscheduled for a course (holding area). */
export async function holdingUnitNames(ctx: VerifyCtx, courseCode: string): Promise<string[]> {
  const courseId = ctx.entities.courses[courseCode];
  if (courseId == null) return [];
  const pending = await api.holdingArea(ctx.sessionId, { kind: "course", courseId });
  return pending.map((p) => p.unit_name ?? "");
}

/** Booking cards for a course's grid (repeating week). */
export async function courseBookings(ctx: VerifyCtx, courseCode: string) {
  const courseId = ctx.entities.courses[courseCode];
  if (courseId == null) return [];
  const grid = await api.timetable(ctx.sessionId, {
    view: "course",
    courseId,
    clashDetect: "off",
  });
  return grid.bookings;
}

/** The booking for (course, unit) if scheduled; undefined otherwise. */
export async function findCourseUnitBooking(
  ctx: VerifyCtx,
  courseCode: string,
  unitName: string,
) {
  const unitId = ctx.entities.units[unitName];
  const bookings = await courseBookings(ctx, courseCode);
  return bookings.find((b) => b.unit_id === unitId);
}

/** URL check helpers (tab/view/selection steps). */
export function urlTab(ctx: VerifyCtx): string {
  return ctx.url.params.get("tab") ?? "timetable";
}

export function urlView(ctx: VerifyCtx): string {
  return ctx.url.params.get("view") ?? "course";
}

export function urlIntParam(ctx: VerifyCtx, key: string): number | null {
  const raw = ctx.url.params.get(key);
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}
