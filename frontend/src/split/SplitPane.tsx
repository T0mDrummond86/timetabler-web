import { useCallback, useEffect, useRef, useState } from "react";
import type { BlockOverview, BookingCard, TimetableGrid } from "../types";
import { BlockOverviewView } from "../components/BlockOverviewView";
import { WeekGridView } from "../components/WeekGridView";
import { api, type Course } from "../api";
import { EditableGroupTitle } from "../components/EditableGroupTitle";
import { showsWeekGrid, isGridEditable, isCourseViewKind, COURSE_VIEW_KINDS, canLoadTimetableGrid } from "../viewKinds";
import { clashDetectForPrefs } from "../lib/displayPrefs";
import type { SlotPaneState } from "./splitLayout";

const COURSE_VIEWS = COURSE_VIEW_KINDS;

type Props = {
  sessionId: number;
  slot: SlotPaneState;
  isActive: boolean;
  colourByClass: boolean;
  showAlerts: boolean;
  autoClashDetect: boolean;
  gridZoom: number;
  onActivate: () => void;
  refreshToken: number;
  onGridLoaded?: (grid: TimetableGrid | null) => void;
  editable?: boolean;
  onMove?: (bookingId: number, column: number, startSlot: number) => void;
  onEdit?: (booking: BookingCard) => void;
  onDismissViolation?: (bookingId: number, code: string) => void;
  onSetClassColour?: (unitId: number, fill: string | null) => void;
  onGroupRenamed?: (course: Course) => void;
  onRenameError?: (message: string) => void;
};

export function SplitPane({
  sessionId,
  slot,
  isActive,
  colourByClass,
  showAlerts,
  autoClashDetect,
  gridZoom,
  onActivate,
  refreshToken,
  onGridLoaded,
  editable: editableProp,
  onMove,
  onEdit,
  onDismissViolation,
  onSetClassColour,
  onGroupRenamed,
  onRenameError,
}: Props) {
  const [grid, setGrid] = useState<TimetableGrid | null>(null);
  const [blockOverview, setBlockOverview] = useState<BlockOverview | null>(null);
  const [title, setTitle] = useState("—");
  const [loading, setLoading] = useState(false);

  const onGridLoadedRef = useRef(onGridLoaded);
  onGridLoadedRef.current = onGridLoaded;

  const slotRef = useRef(slot);
  slotRef.current = slot;

  const loadPane = useCallback(async () => {
    const current = slotRef.current;

    if (current.viewKind === "block_overview") {
      setGrid(null);
      onGridLoadedRef.current?.(null);
      setLoading(true);
      try {
        const overview = await api.blockOverview(sessionId);
        setBlockOverview(overview);
        setTitle("Block groups — overview");
      } catch {
        setBlockOverview(null);
        setTitle("—");
      } finally {
        setLoading(false);
      }
      return;
    }

    setBlockOverview(null);

    if (!showsWeekGrid(current.viewKind)) {
      setGrid(null);
      onGridLoadedRef.current?.(null);
      setTitle("—");
      return;
    }

    if (
      !canLoadTimetableGrid(current.viewKind, {
        courseId: current.courseId,
        staffId: current.staffId,
        blockCourseId: current.blockCourseId,
      })
    ) {
      setGrid(null);
      onGridLoadedRef.current?.(null);
      setTitle(
        current.viewKind === "block_delivery"
          ? "Block delivery — select a group"
          : "Select an item in the sidebar",
      );
      return;
    }

    setLoading(true);
    try {
      const opts: Parameters<typeof api.timetable>[1] = {
        view: current.viewKind,
        colourByClass,
        clashDetect: clashDetectForPrefs({ autoClashDetect }),
      };
      if (COURSE_VIEWS.includes(current.viewKind) && current.courseId) {
        opts.courseId = current.courseId;
      }
      if (current.viewKind === "course" && current.previewSemesterWeek) {
        opts.semesterWeek = current.previewSemesterWeek;
      }
      if (current.viewKind === "block_delivery" && current.blockCourseId) {
        opts.courseId = current.blockCourseId;
        opts.blockWeekIndex = current.blockWeekIndex;
      }
      if (current.viewKind === "staff" && current.staffId) opts.staffId = current.staffId;
      if (current.viewKind === "room" || current.viewKind === "day") opts.day = current.roomDay;
      if (current.viewKind === "course_semester") {
        opts.semesterWeek = current.semesterWeek;
        if (current.courseId) opts.courseId = current.courseId;
      }
      const data = await api.timetable(sessionId, opts);
      setGrid(data);
      onGridLoadedRef.current?.(data);
      setTitle(
        data.course_code ??
          data.entity_label ??
          (data.staff_hours != null
            ? `${data.entity_label ?? "Staff"} — ${data.staff_hours.toFixed(1)} h/week`
            : "Timetable"),
      );
    } catch {
      setGrid(null);
      onGridLoadedRef.current?.(null);
      setTitle("—");
    } finally {
      setLoading(false);
    }
  }, [
    sessionId,
    colourByClass,
    autoClashDetect,
    slot.viewKind,
    slot.courseId,
    slot.staffId,
    slot.roomDay,
    slot.qualificationId,
    slot.blockCourseId,
    slot.blockWeekIndex,
    slot.semesterWeek,
    slot.previewSemesterWeek,
  ]);

  useEffect(() => {
    void loadPane();
  }, [loadPane, refreshToken]);

  const editable =
    isActive && (editableProp ?? (grid ? isGridEditable(slot.viewKind, grid.readonly) : false));

  const renameCourseId =
    slot.viewKind === "block_delivery"
      ? slot.blockCourseId
      : isCourseViewKind(slot.viewKind)
        ? slot.courseId
        : null;
  const renameLabel = grid?.course_code ?? null;

  return (
    <div
      className={`split-pane${isActive ? " split-pane-active" : ""}`}
      onMouseDown={onActivate}
      role="presentation"
    >
      <div className="split-pane-title">
        {renameCourseId != null && renameLabel != null && onGroupRenamed ? (
          <EditableGroupTitle
            sessionId={sessionId}
            courseId={renameCourseId}
            value={renameLabel}
            compact
            onRenamed={onGroupRenamed}
            onError={onRenameError}
          />
        ) : (
          title
        )}
      </div>
      <div className="split-pane-body">
        {slot.viewKind === "block_overview" && (
          <BlockOverviewView
            overview={blockOverview}
            loading={loading}
            onLoadUsage={(cid, week) => api.blockWeekUsage(sessionId, cid, week).catch(() => null)}
          />
        )}
        {grid && (
          <WeekGridView
            grid={grid}
            sessionId={sessionId}
            viewKind={slot.viewKind}
            editable={editable}
            zoom={gridZoom}
            showAlerts={showAlerts}
            onMove={editable ? onMove : undefined}
            onEdit={editable ? onEdit : undefined}
            onDismissViolation={editable && showAlerts ? onDismissViolation : undefined}
            onSetClassColour={editable ? onSetClassColour : undefined}
            colourByClass={colourByClass}
          />
        )}
        {!grid && slot.viewKind !== "block_overview" && loading && (
          <p className="muted split-pane-loading">Loading…</p>
        )}
      </div>
    </div>
  );
}
