export type TimetableMode = "regular" | "block";

export type ViewKind =
  | "course"
  | "course_semester"
  | "staff"
  | "room"
  | "day"
  | "unassigned_lecturer"
  | "block_delivery"
  | "block_overview";

/** Course-scoped timetable views (sidebar course list). */
export const COURSE_VIEW_KINDS: ViewKind[] = ["course", "course_semester"];

export function isCourseViewKind(kind: ViewKind): boolean {
  return COURSE_VIEW_KINDS.includes(kind);
}

export const VIEW_KINDS_BY_MODE: Record<
  TimetableMode,
  { value: ViewKind; label: string }[]
> = {
  regular: [
    { value: "course", label: "Courses" },
    { value: "course_semester", label: "Course (semester weeks)" },
    { value: "staff", label: "Staff" },
    { value: "room", label: "Rooms" },
    { value: "day", label: "Day" },
    { value: "unassigned_lecturer", label: "Unassigned lecturer" },
  ],
  block: [
    { value: "block_delivery", label: "Block delivery" },
    { value: "block_overview", label: "Block groups (overview)" },
  ],
};

export function viewKindMode(kind: ViewKind): TimetableMode {
  if (kind === "block_delivery" || kind === "block_overview") return "block";
  return "regular";
}

export function defaultViewKindForMode(mode: TimetableMode): ViewKind {
  return mode === "block" ? "block_delivery" : "course";
}

export function showsWeekGrid(kind: ViewKind): boolean {
  return kind !== "block_overview";
}

export function showsHoldingArea(kind: ViewKind): boolean {
  return (
    kind === "course" ||
    kind === "course_semester" ||
    kind === "block_delivery" ||
    kind === "unassigned_lecturer"
  );
}

export function isGridEditable(kind: ViewKind, readonly?: boolean): boolean {
  if (readonly) return false;
  return kind !== "day" && kind !== "block_overview";
}

export function entityListViewKind(kind: ViewKind): ViewKind | "block_overview" {
  if (kind === "block_overview") return "block_overview";
  if (kind === "block_delivery") return "block_delivery";
  return kind;
}

/** True when the timetable API has enough context to load this view's grid. */
export function canLoadTimetableGrid(
  kind: ViewKind,
  ids: {
    courseId?: number | null;
    staffId?: number | null;
    blockCourseId?: number | null;
  },
): boolean {
  if (kind === "block_delivery") return ids.blockCourseId != null;
  if (isCourseViewKind(kind) || kind === "course_semester") return ids.courseId != null;
  if (kind === "staff") return ids.staffId != null;
  return true;
}
