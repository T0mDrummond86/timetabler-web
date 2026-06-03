import type { ViewKind } from "../viewKinds";
import { COURSE_VIEW_KINDS, isCourseViewKind } from "../viewKinds";
import type { SlotPaneState } from "./splitLayout";

export function slotSelectedId(slot: SlotPaneState): number | null {
  if (slot.viewKind === "block_delivery") return slot.qualificationId;
  if (COURSE_VIEW_KINDS.includes(slot.viewKind)) return slot.courseId;
  if (slot.viewKind === "staff") return slot.staffId;
  if (slot.viewKind === "day" || slot.viewKind === "room") return slot.roomDay;
  if (slot.viewKind === "block_overview" || slot.viewKind === "unassigned_lecturer") return 0;
  return null;
}

export function applySidebarSelect(slot: SlotPaneState, id: number): SlotPaneState {
  const next = { ...slot };
  if (slot.viewKind === "block_delivery") {
    next.qualificationId = id;
    next.blockCourseId = null;
  } else if (isCourseViewKind(slot.viewKind)) {
    next.courseId = id;
    next.previewSemesterWeek = null;
  } else if (slot.viewKind === "staff") {
    next.staffId = id;
  } else if (slot.viewKind === "day" || slot.viewKind === "room") {
    next.roomDay = id;
  }
  return next;
}

export function patchSlotViewKind(slot: SlotPaneState, kind: ViewKind): SlotPaneState {
  return {
    ...slot,
    viewKind: kind,
    courseId: null,
    staffId: null,
    qualificationId: null,
    blockCourseId: null,
    previewSemesterWeek: null,
  };
}
