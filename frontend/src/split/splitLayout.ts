import type { ViewKind } from "../viewKinds";

export type SplitLayoutKind = "2h" | "2v" | "4";

export type SlotPaneState = {
  viewKind: ViewKind;
  courseId: number | null;
  staffId: number | null;
  roomDay: number;
  qualificationId: number | null;
  blockCourseId: number | null;
  blockWeekIndex: number;
  semesterWeek: number;
  previewSemesterWeek: number | null;
};

export const SPLIT_PANE_LABELS: Record<SplitLayoutKind, string[]> = {
  "2h": ["Grid 1 — left", "Grid 2 — right"],
  "2v": ["Grid 1 — top", "Grid 2 — bottom"],
  "4": ["Grid 1 — top left", "Grid 2 — top right", "Grid 3 — bottom right", "Grid 4 — bottom left"],
};

/** Desktop 4-way DOM order: top row L,R then bottom row L,R (indices 0,1,3,2). */
export const FOUR_WAY_PANE_ORDER = [0, 1, 3, 2] as const;

export const DEFAULT_SLOT_VIEWS: Record<SplitLayoutKind, ViewKind[]> = {
  "2h": ["course", "course_semester"],
  "2v": ["course", "course_semester"],
  "4": ["course", "staff", "course_semester", "room"],
};

export function paneCount(layout: SplitLayoutKind): number {
  return layout === "4" ? 4 : 2;
}

export function initialSlots(layout: SplitLayoutKind): SlotPaneState[] {
  return DEFAULT_SLOT_VIEWS[layout].map((viewKind) => ({
    viewKind,
    courseId: null,
    staffId: null,
    roomDay: 0,
    qualificationId: null,
    blockCourseId: null,
    blockWeekIndex: 1,
    semesterWeek: 1,
    previewSemesterWeek: null,
  }));
}

export function parseSplitLayout(value: string | null): SplitLayoutKind {
  if (value === "2v") return "2v";
  if (value === "4") return "4";
  return "2h";
}
