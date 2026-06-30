import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  Course,
  getToken,
  Qualification,
  Room,
  setToken,
  Staff,
  TimetableGlobalLink,
  TimetableSession,
  Unit,
} from "../api";
import type {
  BlockDeliveryPanel as BlockPanelData,
  BlockOverview,
  BookingCard,
  BookingChange,
  CourseSemesterSchedule,
  CreateBookingDraft,
  HoldingClass,
  TimetableEntity,
  TimetableGrid,
  AlternatePlacementOption,
} from "../types";
import { ScheduleVariantBar } from "../components/ScheduleVariantBar";
import { ViolationsReportPanel } from "../components/ViolationsReportPanel";
import { ClashSettingsPanel } from "../components/ClashSettingsPanel";
import { TimetableViolationsPanel } from "../components/TimetableViolationsPanel";
import { BlockDeliveryPanel } from "../components/BlockDeliveryPanel";
import { BlockOverviewView } from "../components/BlockOverviewView";
import { AppShell } from "../components/AppShell";
import { BookingCreateDialog } from "../components/BookingCreateDialog";
import { BookingEditDialog } from "../components/BookingEditDialog";
import { DataToolbar } from "../components/DataToolbar";
import { EditableGroupTitle } from "../components/EditableGroupTitle";
import { DropdownGroup } from "../components/DropdownGroup";
import { useDropdown } from "../hooks/useDropdown";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";
import type { ViolationRow } from "../types";
import { ClassCustodiansPanel } from "../components/ClassCustodiansPanel";
import { ChangeLogPanel } from "../components/ChangeLogPanel";
import { CourseSemesterPanel } from "../components/CourseSemesterPanel";
import { EntityEditorsPanel } from "../components/EntityEditorsPanel";
import { HoldingAreaPanel } from "../components/HoldingAreaPanel";
import { TimetableSidebar } from "../components/TimetableSidebar";
import { UsageDashboard } from "../components/UsageDashboard";
import { LapCreationPanel } from "../components/LapCreationPanel";
import { LecturerCoverPanel } from "../components/LecturerCoverPanel";
import { LoadingMark } from "../components/LoadingMark";
import { WeekGridView } from "../components/WeekGridView";
import { recordSessionOpen } from "../lib/recentSessions";
import type { TimetableMode, ViewKind } from "../viewKinds";
import {
  canLoadTimetableGrid,
  defaultViewKindForMode,
  entityListViewKind,
  isGridEditable,
  isCourseViewKind,
  showsHoldingArea,
  showsWeekGrid,
  viewKindMode,
  VIEW_KINDS_BY_MODE,
} from "../viewKinds";
import {
  DEFAULT_GRID_ZOOM,
  displayZoomPercent,
  parseZoomUrlParam,
  resetGridZoom,
  zoomIn,
  zoomOut,
} from "../lib/gridZoom";
import { notifySessionChanged, useSessionSync } from "../lib/sessionSync";
import { markGlobalSessionDirty } from "../lib/globalSessionRefresh";
import {
  clashDetectForPrefs,
  readDisplayPrefs,
  writeDisplayPrefs,
  type ClashDetectMode,
} from "../lib/displayPrefs";

type SessionTab =
  | "timetable"
  | "staff"
  | "rooms"
  | "units"
  | "qualifications"
  | "changelog"
  | "warnings"
  | "clash_settings"
  | "custodians"
  | "usage"
  | "lap"
  | "lecturer_cover";

type ViewState = {
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

const SESSION_TABS: { id: SessionTab; label: string; secondary?: boolean }[] = [
  { id: "timetable", label: "Timetable" },
  { id: "warnings", label: "Warnings" },
  { id: "clash_settings", label: "Clash settings" },
  { id: "changelog", label: "Change log" },
  { id: "staff", label: "Staff", secondary: true },
  { id: "lecturer_cover", label: "Lecturer cover", secondary: true },
  { id: "rooms", label: "Rooms", secondary: true },
  { id: "units", label: "Classes", secondary: true },
  { id: "qualifications", label: "Qualifications", secondary: true },
  { id: "custodians", label: "Class custodians", secondary: true },
  { id: "usage", label: "Usage", secondary: true },
  { id: "lap", label: "LAP creation", secondary: true },
];

const ENTITY_SPLIT_TABS = new Set<SessionTab>(["staff", "rooms", "units", "qualifications"]);

const SESSION_TAB_IDS = new Set<SessionTab>(SESSION_TABS.map((t) => t.id));
const VIEW_KIND_IDS = new Set<ViewKind>([
  "course",
  "course_semester",
  "staff",
  "room",
  "day",
  "unassigned_lecturer",
  "block_delivery",
  "block_overview",
]);

function parseIntParam(value: string | null, fallback: number): number {
  if (value == null || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function parseNullableIntParam(value: string | null): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function activeCourseId(state: ViewState): number | null {
  if (state.viewKind === "block_delivery") return state.blockCourseId;
  if (isCourseViewKind(state.viewKind)) return state.courseId;
  return null;
}

export function TimetablePage() {
  const { sessionId: sessionIdParam } = useParams();
  const sessionId = Number(sessionIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [sessions, setSessions] = useState<TimetableSession[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [timetableMode, setTimetableMode] = useState<TimetableMode>("regular");
  const [viewKind, setViewKind] = useState<ViewKind>("course");
  const [courseId, setCourseId] = useState<number | null>(null);
  const [staffId, setStaffId] = useState<number | null>(null);
  const [roomDay, setRoomDay] = useState(0);
  const [qualificationId, setQualificationId] = useState<number | null>(null);
  const [blockCourseId, setBlockCourseId] = useState<number | null>(null);
  const [blockWeekIndex, setBlockWeekIndex] = useState(1);
  const [semesterWeek, setSemesterWeek] = useState(1);
  const [previewSemesterWeek, setPreviewSemesterWeek] = useState<number | null>(null);
  const [gridZoom, setGridZoom] = useState(DEFAULT_GRID_ZOOM);
  const [suggestedBlockCode, setSuggestedBlockCode] = useState<string | null>(null);
  const [sidebarEntities, setSidebarEntities] = useState<TimetableEntity[]>([]);
  const [grid, setGrid] = useState<TimetableGrid | null>(null);
  const [semesterSchedule, setSemesterSchedule] = useState<CourseSemesterSchedule | null>(null);
  const [blockPanel, setBlockPanel] = useState<BlockPanelData | null>(null);
  const [blockOverview, setBlockOverview] = useState<BlockOverview | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [sessionTab, setSessionTab] = useState<SessionTab>("timetable");
  const [focusUnitId, setFocusUnitId] = useState<number | null>(null);
  const [sidebarFilter, setSidebarFilter] = useState("");
  const [changeLogKey, setChangeLogKey] = useState(0);
  const [totalWarningCount, setTotalWarningCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [editBooking, setEditBooking] = useState<BookingCard | null>(null);
  const [undoStack, setUndoStack] = useState<BookingChange[]>([]);
  const [redoStack, setRedoStack] = useState<BookingChange[]>([]);
  const [holding, setHolding] = useState<HoldingClass[]>([]);
  const [importing, setImporting] = useState(false);
  const [importFileName, setImportFileName] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);
  const [holdingLoading, setHoldingLoading] = useState(false);
  const [auxLoading, setAuxLoading] = useState(false);
  const [colourByClass, setColourByClass] = useState(() => readDisplayPrefs().colourByClass);
  const [showAlerts, setShowAlerts] = useState(() => readDisplayPrefs().showAlerts);
  const [autoClashDetect, setAutoClashDetect] = useState(() => readDisplayPrefs().autoClashDetect);
  const [checkingClashes, setCheckingClashes] = useState(false);
  const [createDraft, setCreateDraft] = useState<CreateBookingDraft | null>(null);
  const externalViewsMenu = useDropdown();
  const { confirm, prompt, dialogs } = useConfirmPrompt();
  const [pendingEditBookingId, setPendingEditBookingId] = useState<number | null>(null);
  const [globalLink, setGlobalLink] = useState<TimetableGlobalLink | null>(null);
  const globalLinkRef = useRef(globalLink);
  globalLinkRef.current = globalLink;
  const [entitySyncToken, setEntitySyncToken] = useState(0);
  const importRef = useRef<HTMLInputElement>(null);
  const colourByClassRef = useRef(colourByClass);
  colourByClassRef.current = colourByClass;
  const autoClashDetectRef = useRef(autoClashDetect);
  autoClashDetectRef.current = autoClashDetect;
  const urlReadyRef = useRef(false);
  const applyingUrlRef = useRef(false);
  const sessionInitIdRef = useRef<number | null>(null);

  useEffect(() => {
    const flash = (location.state as { flash?: string } | null)?.flash;
    if (!flash) return;
    setImportSuccess(flash);
    navigate(location.pathname + location.search, { replace: true, state: null });
  }, [location.pathname, location.search, location.state, navigate]);

  const viewState = (): ViewState => ({
    viewKind,
    courseId,
    staffId,
    roomDay,
    qualificationId,
    blockCourseId,
    blockWeekIndex,
    semesterWeek,
    previewSemesterWeek,
  });

  const mutationCourseId = useCallback(
    (booking?: BookingCard | null) => {
      if (booking?.course_id) return booking.course_id;
      const cid = activeCourseId(viewState());
      return cid ?? courses[0]?.id ?? null;
    },
    [viewKind, courseId, blockCourseId, courses],
  );

  const loadSidebarEntities = useCallback(async (sid: number, kind: ViewKind) => {
    const listKind = entityListViewKind(kind);
    const rows = await api.timetableEntities(sid, listKind);
    setSidebarEntities(rows);
    return rows;
  }, []);

  const loadHoldingForView = useCallback(
    async (sid: number, state: ViewState) => {
      if (!showsHoldingArea(state.viewKind)) {
        setHolding([]);
        return;
      }
      setHoldingLoading(true);
      try {
        if (state.viewKind === "unassigned_lecturer") {
          setHolding(await api.holdingArea(sid, { kind: "unassigned" }));
        } else if (state.viewKind === "block_delivery" && state.blockCourseId) {
          setHolding(
            await api.holdingArea(sid, {
              kind: "block",
              courseId: state.blockCourseId,
              blockWeekIndex: state.blockWeekIndex,
            }),
          );
        } else if (state.courseId) {
          setHolding(await api.holdingArea(sid, { kind: "course", courseId: state.courseId }));
        } else {
          setHolding([]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load holding area");
      } finally {
        setHoldingLoading(false);
      }
    },
    [],
  );

  const loadCurrentView = useCallback(
    async (
      sid: number,
      state: ViewState,
      opts?: {
        colourByClass?: boolean;
        clashDetect?: ClashDetectMode;
        refreshSidebar?: boolean;
      },
    ) => {
      const refreshSidebar = opts?.refreshSidebar !== false;
      const sidebarTask = refreshSidebar
        ? loadSidebarEntities(sid, state.viewKind)
        : Promise.resolve();

      const loadMain = async () => {
      if (state.viewKind === "block_overview") {
        setGrid(null);
        setSemesterSchedule(null);
        setBlockPanel(null);
        setAuxLoading(true);
        try {
          setBlockOverview(await api.blockOverview(sid));
        } finally {
          setAuxLoading(false);
        }
        setHolding([]);
        return;
      }

      setBlockOverview(null);

      if (state.viewKind === "course_semester" && state.courseId) {
        setAuxLoading(true);
        try {
          setSemesterSchedule(
            await api.courseSemesterSchedule(sid, state.courseId, state.semesterWeek),
          );
        } finally {
          setAuxLoading(false);
        }
      } else {
        setSemesterSchedule(null);
      }

      if (state.viewKind === "block_delivery" && state.qualificationId) {
        setAuxLoading(true);
        try {
          const panel = await api.blockDeliveryPanel(sid, {
            qualificationId: state.qualificationId,
            courseId: state.blockCourseId,
            blockWeekIndex: state.blockWeekIndex,
          });
          setBlockPanel(panel);
          const sug = await api.suggestedBlockCode(sid, state.qualificationId);
          setSuggestedBlockCode(sug.code);
          if (panel.selected_course_id && panel.selected_course_id !== state.blockCourseId) {
            state = { ...state, blockCourseId: panel.selected_course_id };
            setBlockCourseId(panel.selected_course_id);
          }
          if (panel.block_week_index !== state.blockWeekIndex) {
            state = { ...state, blockWeekIndex: panel.block_week_index };
            setBlockWeekIndex(panel.block_week_index);
          }
        } finally {
          setAuxLoading(false);
        }
      } else {
        setBlockPanel(null);
      }

      if (!showsWeekGrid(state.viewKind)) return;

      if (
        !canLoadTimetableGrid(state.viewKind, {
          courseId: state.courseId,
          staffId: state.staffId,
          blockCourseId: state.blockCourseId,
        })
      ) {
        setGrid(null);
        await loadHoldingForView(sid, state);
        return;
      }

      const timetableOpts: Parameters<typeof api.timetable>[1] = { view: state.viewKind };
      if (isCourseViewKind(state.viewKind) && state.courseId) {
        timetableOpts.courseId = state.courseId;
      }
      if (state.viewKind === "course" && state.previewSemesterWeek) {
        timetableOpts.semesterWeek = state.previewSemesterWeek;
      }
      if (state.viewKind === "block_delivery" && state.blockCourseId) {
        timetableOpts.courseId = state.blockCourseId;
        timetableOpts.blockWeekIndex = state.blockWeekIndex;
      }
      if (state.viewKind === "staff" && state.staffId) timetableOpts.staffId = state.staffId;
      if (state.viewKind === "room") timetableOpts.day = state.roomDay;
      if (state.viewKind === "day") timetableOpts.day = state.roomDay;
      if (state.viewKind === "course_semester") {
        timetableOpts.semesterWeek = state.semesterWeek;
        timetableOpts.courseId = state.courseId;
      }
      timetableOpts.colourByClass = opts?.colourByClass ?? colourByClassRef.current;
      timetableOpts.clashDetect = clashDetectForPrefs(
        { autoClashDetect: autoClashDetectRef.current },
        opts?.clashDetect,
      );

      const data = await api.timetable(sid, timetableOpts);
      setGrid(data);
      await loadHoldingForView(sid, state);
      };

      await Promise.all([sidebarTask, loadMain()]);
    },
    [loadHoldingForView, loadSidebarEntities],
  );

  const loadCurrentViewRef = useRef(loadCurrentView);
  loadCurrentViewRef.current = loadCurrentView;

  const reloadView = useCallback(async () => {
    if (!sessionId) return;
    try {
      await loadCurrentViewRef.current(sessionId, viewState(), {
        colourByClass: colourByClassRef.current,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reload timetable");
    }
  }, [
    sessionId,
    viewKind,
    courseId,
    staffId,
    roomDay,
    qualificationId,
    blockCourseId,
    blockWeekIndex,
    semesterWeek,
    previewSemesterWeek,
  ]);

  const notifyPeers = useCallback(() => {
    notifySessionChanged(sessionId);
  }, [sessionId]);

  useEffect(() => {
    writeDisplayPrefs({ colourByClass, showAlerts, autoClashDetect });
  }, [colourByClass, showAlerts, autoClashDetect]);

  const colourPrefLoaded = useRef(false);
  useEffect(() => {
    if (!colourPrefLoaded.current) {
      colourPrefLoaded.current = true;
      return;
    }
    if (sessionId && sessionTab === "timetable") void reloadView();
  }, [colourByClass, sessionId, sessionTab, reloadView]);

  const applyMutation = useCallback(
    async (change: BookingChange) => {
      setUndoStack((prev) => [...prev, change]);
      setRedoStack([]);
      setChangeLogKey((k) => k + 1);
      await reloadView();
      notifyPeers();
    },
    [reloadView, notifyPeers],
  );

  const resolveCourseId = useCallback(
    (bookingId?: number) => {
      if (bookingId != null && grid) {
        const booking = grid.bookings.find((b) => b.id === bookingId);
        if (booking?.course_id) return booking.course_id;
      }
      return mutationCourseId();
    },
    [grid, mutationCourseId],
  );

  const loadEntities = useCallback(async (sid: number) => {
    const [courseList, staffList, roomList, unitList, qualList] = await Promise.all([
      api.courses(sid),
      api.staff(sid),
      api.rooms(sid),
      api.units(sid),
      api.qualifications(sid),
    ]);
    setCourses(courseList);
    setStaff(staffList);
    setRooms(roomList);
    setUnits(unitList);
    setQualifications(qualList);
    return { courseList, staffList, roomList };
  }, []);

  type EntityUpdateHint = {
    blockCourseId?: number;
    qualificationId?: number;
  };

  const onEntityUpdated = useCallback(
    (hint?: EntityUpdateHint) => {
      void loadEntities(sessionId).then(() => {
        if (hint?.blockCourseId != null) setBlockCourseId(hint.blockCourseId);
        if (hint?.qualificationId != null) setQualificationId(hint.qualificationId);
        if (sessionTab === "timetable") void reloadView();
        notifyPeers();
      });
    },
    [sessionId, sessionTab, loadEntities, reloadView, notifyPeers],
  );

  const refreshHolding = useCallback(async () => {
    await loadHoldingForView(sessionId, viewState());
  }, [sessionId, loadHoldingForView, viewKind, courseId, blockCourseId, blockWeekIndex]);

  useSessionSync(sessionId, () => {
    void reloadView();
    void loadSidebarEntities(sessionId, viewKind);
    setEntitySyncToken((t) => t + 1);
    setChangeLogKey((k) => k + 1);
    void refreshHolding();
  });

  useEffect(() => {
    return () => {
      const link = globalLinkRef.current;
      if (link?.linked && link.global_session_id) {
        markGlobalSessionDirty(link.global_session_id);
      }
    };
  }, [sessionId]);

  const refreshWarningCount = useCallback(async () => {
    try {
      const report = await api.violationsReport(sessionId);
      setTotalWarningCount(report.rows.length);
    } catch {
      setTotalWarningCount(0);
    }
  }, [sessionId]);

  useEffect(() => {
    void refreshWarningCount();
  }, [refreshWarningCount, changeLogKey]);

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    if (!sessionId) {
      setError("Invalid session");
      setLoading(false);
      return;
    }
    if (sessionInitIdRef.current === sessionId) return;
    sessionInitIdRef.current = sessionId;
    recordSessionOpen(sessionId);
    urlReadyRef.current = false;

    (async () => {
      try {
        const orgs = await api.orgs();
        if (!orgs.length) throw new Error("No organization");
        const sess = await api.sessions(orgs[0].id);
        setSessions(sess);
        const { courseList, staffList } = await loadEntities(sessionId);
        if (!courseList.length) {
          setLoading(false);
          urlReadyRef.current = true;
          return;
        }
        const rawView = searchParams.get("view");
        const parsedView: ViewKind =
          rawView === "co_teach"
            ? "course"
            : rawView && VIEW_KIND_IDS.has(rawView as ViewKind)
              ? (rawView as ViewKind)
              : "course";
        const parsedTabRaw = searchParams.get("tab");
        const parsedTab: SessionTab =
          parsedTabRaw && SESSION_TAB_IDS.has(parsedTabRaw as SessionTab)
            ? (parsedTabRaw as SessionTab)
            : "timetable";
        const parsedCourseId = parseNullableIntParam(searchParams.get("course"));
        const parsedStaffId = parseNullableIntParam(searchParams.get("staff"));
        const parsedRoomDay = parseIntParam(searchParams.get("day"), 0);
        const parsedQualId = parseNullableIntParam(searchParams.get("qualification"));
        const parsedBlockCourseId = parseNullableIntParam(searchParams.get("blockCourse"));
        const parsedBlockWeek = parseIntParam(searchParams.get("blockWeek"), 1);
        const parsedSemesterWeek = parseIntParam(searchParams.get("semesterWeek"), 1);
        const parsedPreviewWeek = parseNullableIntParam(searchParams.get("previewWeek"));
        const cid = parsedCourseId ?? courseList[0]?.id ?? null;
        const sid = parsedStaffId ?? staffList[0]?.id ?? null;
        setSessionTab(parsedTab);
        setViewKind(parsedView);
        setTimetableMode(viewKindMode(parsedView));
        setCourseId(cid);
        setStaffId(sid);
        setRoomDay(Math.max(0, Math.min(4, parsedRoomDay)));
        setQualificationId(parsedQualId);
        setBlockCourseId(parsedBlockCourseId);
        setBlockWeekIndex(Math.max(1, parsedBlockWeek));
        setSemesterWeek(Math.max(1, parsedSemesterWeek));
        setPreviewSemesterWeek(parsedPreviewWeek);
        setGridZoom(parseZoomUrlParam(searchParams.get("zoom")));
        const initial: ViewState = {
          viewKind: parsedView,
          courseId: cid,
          staffId: sid,
          roomDay: Math.max(0, Math.min(4, parsedRoomDay)),
          qualificationId: parsedQualId,
          blockCourseId: parsedBlockCourseId,
          blockWeekIndex: Math.max(1, parsedBlockWeek),
          semesterWeek: Math.max(1, parsedSemesterWeek),
          previewSemesterWeek: parsedPreviewWeek,
        };
        if (activeCourseId(initial) != null || initial.viewKind === "staff" || initial.viewKind === "day" || initial.viewKind === "room" || initial.viewKind === "unassigned_lecturer" || initial.viewKind === "block_overview") {
          await loadCurrentViewRef.current(sessionId, initial, {
            colourByClass: colourByClassRef.current,
          });
        }
        urlReadyRef.current = true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to load";
        setError(msg);
        if (msg.includes("Session not found")) {
          navigate("/dashboard");
        } else if (
          msg.includes("401") ||
          msg.includes("Not authenticated") ||
          msg.includes("Invalid token")
        ) {
          setToken(null);
          navigate("/login");
        }
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once per session; URL read at mount
  }, [sessionId, navigate, loadEntities]);

  useEffect(() => {
    if (!urlReadyRef.current || applyingUrlRef.current) return;
    const params = new URLSearchParams(location.search);
    params.set("tab", sessionTab);
    params.set("view", viewKind);
    const zoomDisplay = displayZoomPercent(gridZoom);
    if (zoomDisplay === displayZoomPercent(DEFAULT_GRID_ZOOM)) {
      params.delete("zoom");
    } else {
      params.set("zoom", String(zoomDisplay));
    }
    if (courseId != null) params.set("course", String(courseId));
    else params.delete("course");
    if (staffId != null) params.set("staff", String(staffId));
    else params.delete("staff");
    params.set("day", String(roomDay));
    if (qualificationId != null) params.set("qualification", String(qualificationId));
    else params.delete("qualification");
    if (blockCourseId != null) params.set("blockCourse", String(blockCourseId));
    else params.delete("blockCourse");
    params.set("blockWeek", String(blockWeekIndex));
    params.set("semesterWeek", String(semesterWeek));
    if (previewSemesterWeek != null) params.set("previewWeek", String(previewSemesterWeek));
    else params.delete("previewWeek");
    const next = params.toString();
    const curr = location.search.startsWith("?") ? location.search.slice(1) : location.search;
    if (next !== curr) {
      applyingUrlRef.current = true;
      setSearchParams(params, { replace: true });
      queueMicrotask(() => {
        applyingUrlRef.current = false;
      });
    }
  }, [
    location.search,
    setSearchParams,
    sessionTab,
    viewKind,
    courseId,
    staffId,
    roomDay,
    qualificationId,
    blockCourseId,
    blockWeekIndex,
    semesterWeek,
    previewSemesterWeek,
    gridZoom,
  ]);

  function shouldRefreshSidebar(partial: Partial<ViewState>): boolean {
    if (partial.viewKind != null) return true;
    if (partial.qualificationId !== undefined && viewKind === "block_delivery") return true;
    return false;
  }

  async function applyViewChange(partial: Partial<ViewState>) {
    const next = { ...viewState(), ...partial };
    const entityOnly =
      partial.viewKind == null &&
      partial.qualificationId === undefined &&
      (partial.staffId !== undefined ||
        partial.courseId !== undefined ||
        partial.roomDay !== undefined ||
        partial.blockCourseId !== undefined ||
        partial.semesterWeek !== undefined ||
        partial.previewSemesterWeek !== undefined ||
        partial.blockWeekIndex !== undefined);
    if (!entityOnly || !grid) setLoading(true);
    setUndoStack([]);
    setRedoStack([]);
    setError(null);
    if (partial.viewKind != null) setViewKind(partial.viewKind);
    if (partial.courseId !== undefined) setCourseId(partial.courseId);
    if (partial.staffId !== undefined) setStaffId(partial.staffId);
    if (partial.roomDay !== undefined) setRoomDay(partial.roomDay);
    if (partial.qualificationId !== undefined) setQualificationId(partial.qualificationId);
    if (partial.blockCourseId !== undefined) setBlockCourseId(partial.blockCourseId);
    if (partial.blockWeekIndex !== undefined) setBlockWeekIndex(partial.blockWeekIndex);
    if (partial.semesterWeek !== undefined) setSemesterWeek(partial.semesterWeek);
    if (partial.previewSemesterWeek !== undefined) setPreviewSemesterWeek(partial.previewSemesterWeek);
    try {
      await loadCurrentViewRef.current(sessionId, next, {
        colourByClass: colourByClassRef.current,
        refreshSidebar: shouldRefreshSidebar(partial),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  async function onModeChange(mode: TimetableMode) {
    setSidebarFilter("");
    setTimetableMode(mode);
    const kind = defaultViewKindForMode(mode);
    await applyViewChange({
      viewKind: kind,
      qualificationId: mode === "block" ? qualificationId ?? sidebarEntities[0]?.id ?? null : null,
    });
  }

  async function onViewKindChange(kind: ViewKind) {
    setSidebarFilter("");
    setTimetableMode(viewKindMode(kind));
    const partial: Partial<ViewState> = { viewKind: kind };
    if (kind === "block_delivery" && !qualificationId && sidebarEntities.length) {
      partial.qualificationId = sidebarEntities[0].id;
    }
    if (kind === "day" || kind === "room") {
      partial.roomDay = roomDay;
    }
    await applyViewChange(partial);
  }

  async function onPreviewWeekChange(week: number | null) {
    await applyViewChange({ previewSemesterWeek: week });
  }

  async function onSidebarSelect(id: number) {
    if (viewKind === "block_delivery") {
      await applyViewChange({ qualificationId: id, blockCourseId: null });
      return;
    }
    if (isCourseViewKind(viewKind)) {
      await applyViewChange({ courseId: id, previewSemesterWeek: null });
      return;
    }
    if (viewKind === "staff") await applyViewChange({ staffId: id });
    if (viewKind === "day" || viewKind === "room") await applyViewChange({ roomDay: id });
  }

  function openAdditionalTab() {
    window.open(window.location.href, "_blank", "noopener,noreferrer");
  }

  function buildExternalViewUrl(kind: ViewKind): string {
    const params = new URLSearchParams();
    params.set("tab", "timetable");
    params.set("view", kind);
    if (kind === "room" || kind === "day") {
      params.set("day", String(roomDay));
    }
    if (isCourseViewKind(kind) && courseId != null) {
      params.set("course", String(courseId));
    }
    if (kind === "staff" && staffId != null) {
      params.set("staff", String(staffId));
    }
    if (kind === "block_delivery") {
      if (qualificationId != null) params.set("qualification", String(qualificationId));
      if (blockCourseId != null) params.set("blockCourse", String(blockCourseId));
      params.set("blockWeek", String(blockWeekIndex));
    }
    return `/timetable/${sessionId}?${params.toString()}`;
  }

  function openViewInNewTab(kind: ViewKind) {
    externalViewsMenu.close();
    window.open(buildExternalViewUrl(kind), "_blank", "noopener,noreferrer");
  }

  function openSplit(layout: "2h" | "2v" | "4") {
    externalViewsMenu.close();
    window.open(`/timetable/${sessionId}/split?layout=${layout}`, "_blank", "noopener,noreferrer");
  }

  async function onSemesterWeekSelect(week: number) {
    await applyViewChange({ semesterWeek: week });
  }

  async function onToggleSemesterWeek(bookingId: number, week: number) {
    setMutating(true);
    try {
      const schedule = await api.toggleSemesterWeek(sessionId, {
        booking_id: bookingId,
        semester_week: week,
      });
      setSemesterSchedule(schedule);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Toggle week failed");
    } finally {
      setMutating(false);
    }
  }

  async function onBlockCourseChange(cid: number) {
    await applyViewChange({ blockCourseId: cid });
  }

  async function onBlockWeekChange(idx: number) {
    await applyViewChange({ blockWeekIndex: idx });
  }

  async function onBlockCoursePatch(patch: {
    block_week_count?: number;
    block_start_semester_week?: number;
  }) {
    if (!blockCourseId) return;
    setMutating(true);
    setError(null);
    try {
      await api.patchCourse(sessionId, blockCourseId, patch);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update block settings failed");
    } finally {
      setMutating(false);
    }
  }

  async function onDuplicateBlockGroup(newCode: string) {
    if (!blockCourseId || !newCode.trim()) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.duplicateBlockGroup(sessionId, blockCourseId, newCode.trim());
      await applyViewChange({ blockCourseId: result.course_id });
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Duplicate group failed");
    } finally {
      setMutating(false);
    }
  }

  async function onDeleteBlockGroup() {
    if (!blockCourseId) return;
    if (
      !(await confirm({
        title: "Delete block group",
        message: "Delete this block group and its timetable? This cannot be undone.",
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
    setMutating(true);
    setError(null);
    try {
      await api.deleteBlockGroup(sessionId, blockCourseId);
      await applyViewChange({ blockCourseId: null });
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete group failed");
    } finally {
      setMutating(false);
    }
  }

  async function onSetClassColour(unitId: number, fill: string | null) {
    setMutating(true);
    setError(null);
    try {
      await api.patchUnit(sessionId, unitId, { screen_fill_colour: fill });
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Class colour update failed");
    } finally {
      setMutating(false);
    }
  }

  async function onToggleLock(booking: BookingCard, field: "lock_time" | "lock_staff") {
    const cid = mutationCourseId(booking);
    if (!cid) return;
    setMutating(true);
    setError(null);
    try {
      const patch =
        field === "lock_time"
          ? { lock_time: booking.lock_time ? 0 : 1 }
          : { lock_staff: booking.lock_staff ? 0 : 1 };
      const result = await api.patchBookingLocks(sessionId, booking.id, { course_id: cid, ...patch });
      await applyMutation(result.change);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lock toggle failed");
    } finally {
      setMutating(false);
    }
  }

  async function onMergeClasses(bookingIds: number[]) {
    setMutating(true);
    setError(null);
    try {
      await api.mergeClasses(sessionId, bookingIds);
      await reloadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setMutating(false);
    }
  }

  async function onUnmergeClasses(bookingId: number) {
    setMutating(true);
    setError(null);
    try {
      await api.unmergeClasses(sessionId, bookingId);
      await reloadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unmerge failed");
    } finally {
      setMutating(false);
    }
  }

  async function onAlternateMove(booking: BookingCard, option: AlternatePlacementOption) {
    const cid = mutationCourseId(booking);
    if (!cid) return;
    const duration = booking.end_slot - booking.start_slot;
    setMutating(true);
    setError(null);
    try {
      const patch: Parameters<typeof api.patchBooking>[2] = {
        course_id: cid,
        day: option.day,
        start_slot: option.start_slot,
        end_slot: option.start_slot + duration,
        room_id: option.room_id,
      };
      if (option.staff_id != null) {
        patch.staff_id = option.staff_id;
      }
      const result = await api.patchBooking(sessionId, booking.id, patch);
      await applyMutation(result.change);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move failed");
    } finally {
      setMutating(false);
    }
  }

  async function onSidebarReorder(direction: -1 | 1) {
    const orderView =
      viewKind === "staff"
        ? "staff"
        : isCourseViewKind(viewKind)
          ? "course"
          : null;
    if (!orderView) return;
    const selected = sidebarSelectedId;
    if (selected == null) return;
    const idx = sidebarEntities.findIndex((e) => e.id === selected);
    if (idx < 0) return;
    const swapIdx = idx + direction;
    if (swapIdx < 0 || swapIdx >= sidebarEntities.length) return;
    const next = [...sidebarEntities];
    [next[idx], next[swapIdx]] = [next[swapIdx], next[idx]];
    setMutating(true);
    setError(null);
    try {
      await api.sidebarOrder(sessionId, { view: orderView, entity_ids: next.map((e) => e.id) });
      setSidebarEntities(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reorder failed");
    } finally {
      setMutating(false);
    }
  }

  async function onSeedDemo() {
    setSeeding(true);
    setError(null);
    try {
      await api.seedDemo(sessionId);
      const { courseList, staffList } = await loadEntities(sessionId);
      const cid = courseList[0]?.id ?? null;
      const sid = staffList[0]?.id ?? null;
      await applyViewChange({ courseId: cid, staffId: sid });
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  }

  async function onPlacePending(item: HoldingClass, day: number, startSlot: number) {
    const cid =
      viewKind === "unassigned_lecturer"
        ? item.course_id
        : viewKind === "block_delivery"
          ? blockCourseId
          : courseId;
    if (!cid) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.createBooking(sessionId, {
        course_id: cid,
        unit_id: item.unit_id,
        day,
        start_slot: startSlot,
        end_slot: startSlot + item.duration_slots,
        session_part: item.session_part,
        block_week_index: viewKind === "block_delivery" ? blockWeekIndex : undefined,
      });
      await applyMutation(result.change);
      await refreshHolding();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Place failed");
    } finally {
      setMutating(false);
    }
  }

  async function onReturnToHolding(bookingId: number) {
    const booking = grid?.bookings.find((b) => b.id === bookingId);
    const cid = mutationCourseId(booking);
    if (!cid) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.deleteBooking(sessionId, bookingId, cid);
      await applyMutation(result.change);
      await refreshHolding();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not return to holding area");
    } finally {
      setMutating(false);
    }
  }

  async function onDeletePlacecard(booking: BookingCard) {
    const cid = mutationCourseId(booking);
    if (!cid) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.deleteBooking(sessionId, booking.id, cid);
      await applyMutation(result.change);
      await refreshHolding();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete class");
    } finally {
      setMutating(false);
    }
  }

  async function onImportFile(
    kind: "session" | "qualifications" | "qualifications-csp" | "qualifications-ep-nb-csp" | "asc" | "lecturer-preferences" | "overall-visual" | "admin-visual",
    file: File,
  ) {
    setImporting(true);
    setImportFileName(file.name);
    setImportSuccess(null);
    setError(null);
    try {
      if (kind === "session") {
        const report = await api.importSession(sessionId, file);
        const { courseList, staffList } = await loadEntities(sessionId);
        setUndoStack([]);
        setRedoStack([]);
        await applyViewChange({
          courseId: courseList[0]?.id ?? null,
          staffId: staffList[0]?.id ?? null,
        });
        setImportSuccess(
          `Imported ${report.bookings} bookings, ${report.courses} courses, ${report.staff} staff from ${file.name}.`,
        );
        notifyPeers();
      } else {
        const report = (await api.importFile(sessionId, kind, file)) as Record<string, unknown>;
        await loadEntities(sessionId);
        await reloadView();
        setChangeLogKey((k) => k + 1);
        notifyPeers();
        const bookings = report.bookings_written ?? report.bookings;
        const parts: string[] = [];
        if (typeof bookings === "number") parts.push(`${bookings} bookings`);
        if (typeof report.classes_created === "number" && report.classes_created > 0) {
          parts.push(`${report.classes_created} new classes`);
        }
        if (typeof report.staff_created === "number" && report.staff_created > 0) {
          parts.push(`${report.staff_created} staff`);
        }
        if (typeof report.rooms_created === "number" && report.rooms_created > 0) {
          parts.push(`${report.rooms_created} rooms`);
        }
        if (typeof report.units_created === "number" && report.units_created > 0) {
          parts.push(`${report.units_created} new classes`);
        }
        if (typeof report.qualifications_created === "number" && report.qualifications_created > 0) {
          parts.push(`${report.qualifications_created} qualifications`);
        }
        setImportSuccess(
          parts.length
            ? `Import complete: ${parts.join(", ")} from ${file.name}.`
            : `Import from ${file.name} completed successfully.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      setImportFileName(null);
    }
  }

  async function onCreateBooking(body: {
    unit_id: number;
    day: number;
    start_slot: number;
    end_slot: number;
    staff_id?: number | null;
    room_id?: number | null;
    notes?: string | null;
  }) {
    const cid = mutationCourseId();
    if (!cid) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.createBooking(sessionId, {
        course_id: cid,
        ...body,
        block_week_index: viewKind === "block_delivery" ? blockWeekIndex : undefined,
      });
      await applyMutation(result.change);
      setCreateDraft(null);
      await refreshHolding();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setMutating(false);
    }
  }

  async function onDismissViolation(bookingId: number, code: string) {
    try {
      await api.dismissViolation(sessionId, bookingId, code);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dismiss failed");
    }
  }

  async function onStaffToggleLock() {
    if (!staffId) return;
    const row = staff.find((s) => s.id === staffId);
    if (!row) return;
    setMutating(true);
    try {
      await api.patchStaff(sessionId, staffId, {
        timetable_locked: row.timetable_locked ? 0 : 1,
      });
      await loadEntities(sessionId);
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lock failed");
    } finally {
      setMutating(false);
    }
  }

  async function onCheckClashes() {
    if (!sessionId) return;
    setCheckingClashes(true);
    setError(null);
    try {
      await loadCurrentViewRef.current(sessionId, viewState(), {
        colourByClass: colourByClassRef.current,
        clashDetect: "once",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clash check failed");
    } finally {
      setCheckingClashes(false);
    }
  }

  async function onMove(bookingId: number, column: number, startSlot: number) {
    const booking = grid?.bookings.find((b) => b.id === bookingId);
    const cid = mutationCourseId(booking);
    if (!cid || !grid) return;
    setMutating(true);
    setError(null);
    try {
      if (grid.column_kind === "room") {
        const room = rooms[column];
        if (!room) return;
        const result = await api.moveBooking(sessionId, bookingId, {
          course_id: cid,
          day: grid.focus_day ?? roomDay,
          start_slot: startSlot,
          room_id: room.id,
        });
        await applyMutation(result.change);
      } else {
        const result = await api.moveBooking(sessionId, bookingId, {
          course_id: cid,
          day: column,
          start_slot: startSlot,
        });
        await applyMutation(result.change);
      }
      await refreshHolding();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move failed");
      await reloadView();
    } finally {
      setMutating(false);
    }
  }

  async function onSaveEdit(
    patch: Omit<Parameters<typeof api.patchBooking>[2], "course_id">,
  ) {
    const cid = mutationCourseId(editBooking);
    if (!cid || !editBooking) return;
    setMutating(true);
    setError(null);
    try {
      const result = await api.patchBooking(sessionId, editBooking.id, {
        course_id: cid,
        ...patch,
      });
      await applyMutation(result.change);
      setEditBooking(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setMutating(false);
    }
  }

  async function onCourseAdd() {
    const code = await prompt({ title: "New course", placeholder: "Course code" });
    if (!code) return;
    setMutating(true);
    try {
      const row = await api.createCourse(sessionId, code.trim());
      await applyViewChange({ courseId: row.id, previewSemesterWeek: null });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add course failed");
    } finally {
      setMutating(false);
    }
  }

  async function onCourseDuplicate() {
    if (!courseId) return;
    const src = courses.find((c) => c.id === courseId);
    const newCode = await prompt({
      title: "Duplicate course",
      defaultValue: src ? `${src.code} (copy)` : "",
      placeholder: "Course code",
    });
    if (!newCode) return;
    setMutating(true);
    try {
      const row = await api.duplicateCourse(sessionId, courseId, newCode.trim());
      await applyViewChange({ courseId: row.id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Duplicate course failed");
    } finally {
      setMutating(false);
    }
  }

  async function onCourseDelete() {
    if (!courseId) return;
    const src = courses.find((c) => c.id === courseId);
    if (
      !(await confirm({
        title: "Delete course",
        message: `Delete course ${src?.code ?? courseId} and all its bookings?`,
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
    setMutating(true);
    try {
      await api.deleteCourse(sessionId, courseId);
      const next = courses.find((c) => c.id !== courseId)?.id ?? null;
      await loadEntities(sessionId);
      await applyViewChange({ courseId: next, previewSemesterWeek: null });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete course failed");
    } finally {
      setMutating(false);
    }
  }

  async function onCourseToggleLock() {
    if (!courseId) return;
    const src = courses.find((c) => c.id === courseId);
    if (!src) return;
    setMutating(true);
    try {
      await api.patchCourse(sessionId, courseId, {
        timetable_locked: src.timetable_locked ? 0 : 1,
      });
      await loadEntities(sessionId);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lock toggle failed");
    } finally {
      setMutating(false);
    }
  }

  const onGroupRenamed = useCallback(
    async (updated: Course) => {
      setCourses((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      await loadEntities(sessionId);
      await reloadView();
      notifyPeers();
    },
    [sessionId, loadEntities, reloadView, notifyPeers],
  );

  async function undo() {
    const cid = mutationCourseId();
    if (!cid || undoStack.length === 0 || mutating) return;
    const entry = undoStack[undoStack.length - 1];
    setMutating(true);
    setError(null);
    try {
      await api.restoreBookings(sessionId, {
        course_id: cid,
        action: "undo",
        label: entry.description,
        snapshots: entry.before,
      });
      setUndoStack((prev) => prev.slice(0, -1));
      setRedoStack((prev) => [...prev, entry]);
      setChangeLogKey((k) => k + 1);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo failed");
    } finally {
      setMutating(false);
    }
  }

  async function redo() {
    const cid = mutationCourseId();
    if (!cid || redoStack.length === 0 || mutating) return;
    const entry = redoStack[redoStack.length - 1];
    setMutating(true);
    setError(null);
    try {
      await api.restoreBookings(sessionId, {
        course_id: cid,
        action: "redo",
        label: entry.description,
        snapshots: entry.after,
      });
      setRedoStack((prev) => prev.slice(0, -1));
      setUndoStack((prev) => [...prev, entry]);
      setChangeLogKey((k) => k + 1);
      await reloadView();
      notifyPeers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Redo failed");
    } finally {
      setMutating(false);
    }
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        void undo();
      }
      if (e.key === "z" && e.shiftKey) {
        e.preventDefault();
        void redo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const sessionName = sessions.find((s) => s.id === sessionId)?.name ?? `Session #${sessionId}`;

  const sidebarSelectedId = (() => {
    if (viewKind === "block_delivery") return qualificationId;
    if (isCourseViewKind(viewKind)) return courseId;
    if (viewKind === "staff") return staffId;
    if (viewKind === "day" || viewKind === "room") return roomDay;
    if (viewKind === "block_overview") return 0;
    if (viewKind === "unassigned_lecturer") return 0;
    return null;
  })();

  const groupRenameCourseId =
    sessionTab === "timetable"
      ? viewKind === "block_delivery"
        ? blockCourseId
        : isCourseViewKind(viewKind)
          ? courseId
          : null
      : null;

  const groupRenameLabel =
    groupRenameCourseId != null
      ? grid?.course_code ?? courses.find((c) => c.id === groupRenameCourseId)?.code ?? "—"
      : null;

  const pageTitle =
    sessionTab !== "timetable"
      ? SESSION_TABS.find((t) => t.id === sessionTab)?.label ?? "Session"
      : viewKind === "block_overview"
        ? "Block groups (overview)"
        : viewKind === "staff" && grid?.staff_hours != null
          ? `${grid.entity_label ?? "Staff"} — ${grid.staff_hours.toFixed(1)} h/week`
          : groupRenameCourseId != null && groupRenameLabel != null
            ? (
                <EditableGroupTitle
                  sessionId={sessionId}
                  courseId={groupRenameCourseId}
                  value={groupRenameLabel}
                  onRenamed={(c) => void onGroupRenamed(c)}
                  onError={setError}
                />
              )
            : grid?.course_code ?? grid?.entity_label ?? "Timetable";

  const sidebarReorderable = isCourseViewKind(viewKind) || viewKind === "staff";
  const staffAdmin = viewKind === "staff";
  const activeStaff = staff.find((s) => s.id === staffId);

  const courseAdmin = isCourseViewKind(viewKind);
  const activeCourse = courses.find((c) => c.id === courseId);

  const editable = grid ? isGridEditable(viewKind, grid.readonly) : false;

  const goToWarningBooking = useCallback(
    async (bookingId: number, row: ViolationRow) => {
      setSessionTab("timetable");
      setPendingEditBookingId(bookingId);
      const course = courses.find((c) => c.code === row.group);
      if (course) {
        await applyViewChange({ viewKind: "course", courseId: course.id });
      }
    },
    [courses, applyViewChange],
  );

  useEffect(() => {
    if (pendingEditBookingId == null || !grid) return;
    const booking = grid.bookings.find((b) => b.id === pendingEditBookingId);
    if (booking) {
      setEditBooking(booking);
      setPendingEditBookingId(null);
    }
  }, [grid, pendingEditBookingId]);

  useEffect(() => {
    if (!sessionId) return;
    void api.timetableGlobalLink(sessionId).then(setGlobalLink).catch(() => setGlobalLink(null));
  }, [sessionId]);
  const canPlacePending = showsHoldingArea(viewKind) && editable;
  const canCreateOnGrid =
    editable &&
    (isCourseViewKind(viewKind) || viewKind === "block_delivery");

  const isEmbedded = searchParams.get("embed") === "1";
  const warningCount = totalWarningCount;

  return (
    <AppShell
      wide
      minimal={isEmbedded}
      fillViewport={
        (sessionTab === "timetable" && courses.length > 0) || ENTITY_SPLIT_TABS.has(sessionTab)
      }
      breadcrumb={
        <>
          <Link to="/dashboard">Dashboard</Link>
          <span aria-hidden> / </span>
          {sessionName}
        </>
      }
      title={pageTitle}
      subtitle={
        sessionTab === "timetable" && viewKind !== "block_overview" ? (
          <span className="tt-page-subtitle">
            {grid?.week_label ?? "Repeating week"}
            {editable ? (
              <span className="tt-edit-hint">Drag to move · Double-click to edit</span>
            ) : (
              <span className="tt-readonly-badge" role="status">
                Read-only — viewing only
              </span>
            )}
            {globalLink?.linked && viewKind === "staff" && (
              <span className="tt-global-link-hint muted">
                Dark grey = scheduled in linked session
                {globalLink.global_session_name ? ` (${globalLink.global_session_name})` : ""}.{" "}
                <Link to={`/global/${globalLink.global_session_id}`}>Global group</Link>
              </span>
            )}
          </span>
        ) : undefined
      }
      actions={
        mutating ? (
          <span className="muted" style={{ fontSize: "0.85rem" }}>
            Saving…
          </span>
        ) : undefined
      }
    >
      <DropdownGroup>
      <div className="tt-toolbar">
        {sessionTab === "timetable" && (
        <div className="tt-toolbar-group">
          <span className="tt-toolbar-label">Schedule</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void undo()}
            disabled={!undoStack.length || mutating}
            title="Undo (⌘Z)"
          >
            Undo
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void redo()}
            disabled={!redoStack.length || mutating}
            title="Redo (⌘⇧Z)"
          >
            Redo
          </button>
          <button type="button" className="btn-secondary" onClick={openAdditionalTab}>
            New tab
          </button>
          {!isEmbedded && (
            <span className="tt-dropdown-wrap" ref={externalViewsMenu.wrapRef}>
              <button
                type="button"
                className="btn-secondary"
                onClick={externalViewsMenu.toggle}
                aria-expanded={externalViewsMenu.open}
                aria-haspopup="menu"
                title="Open the same timetable view in a new browser tab or split layout"
              >
                Open in new tab ▾
              </button>
              {externalViewsMenu.open && (
                <div className="tt-dropdown-menu" role="menu">
                  <span className="ctx-label">New browser tab</span>
                  {[...VIEW_KINDS_BY_MODE.regular, ...VIEW_KINDS_BY_MODE.block].map((opt) => (
                    <button
                      key={`ext-${opt.value}`}
                      type="button"
                      className="ctx-item"
                      onClick={() => {
                        externalViewsMenu.close();
                        openViewInNewTab(opt.value);
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                  <div className="ctx-divider" />
                  <span className="ctx-label">Split layout (this session)</span>
                  <button
                    type="button"
                    className="ctx-item"
                    role="menuitem"
                    onClick={() => {
                      externalViewsMenu.close();
                      openSplit("4");
                    }}
                  >
                    4-way
                  </button>
                  <button
                    type="button"
                    className="ctx-item"
                    role="menuitem"
                    onClick={() => {
                      externalViewsMenu.close();
                      openSplit("2h");
                    }}
                  >
                    2-way side-by-side
                  </button>
                  <button
                    type="button"
                    className="ctx-item"
                    role="menuitem"
                    onClick={() => {
                      externalViewsMenu.close();
                      openSplit("2v");
                    }}
                  >
                    2-way stacked
                  </button>
                </div>
              )}
            </span>
          )}
          {showsWeekGrid(viewKind) && (
            <>
              <span className="tt-toolbar-sep" aria-hidden />
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => setGridZoom((z) => zoomOut(z))}
                aria-label="Zoom out"
                title="Zoom out"
              >
                −
              </button>
              <span className="tt-zoom-label">{displayZoomPercent(gridZoom)}%</span>
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => setGridZoom((z) => zoomIn(z))}
                aria-label="Zoom in"
                title="Zoom in"
              >
                +
              </button>
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => setGridZoom(resetGridZoom())}
                aria-label="Reset zoom"
                title="Reset zoom"
              >
                100%
              </button>
            </>
          )}
        </div>
        )}
        <DataToolbar
          sessionId={sessionId}
          colourByClass={colourByClass}
          onColourByClassChange={setColourByClass}
          showAlerts={showAlerts}
          onShowAlertsChange={setShowAlerts}
          autoClashDetect={autoClashDetect}
          onAutoClashDetectChange={(v) => {
            autoClashDetectRef.current = v;
            setAutoClashDetect(v);
            if (sessionId && sessionTab === "timetable") {
              void loadCurrentViewRef.current(sessionId, viewState(), {
                colourByClass: colourByClassRef.current,
              });
            }
          }}
          onCheckClashes={() => void onCheckClashes()}
          checkingClashes={checkingClashes}
          onImport={(kind, file) => void onImportFile(kind, file)}
          onError={setError}
          importing={importing}
          showDisplay={sessionTab === "timetable"}
        />
      </div>
      </DropdownGroup>

      <nav className="session-tabs" aria-label="Session views">
        {SESSION_TABS.map((tab, index) => (
          <span key={tab.id} style={{ display: "contents" }}>
            {index === 4 && <span className="session-tab-divider" aria-hidden />}
            <button
              type="button"
              className={`session-tab${sessionTab === tab.id ? " active" : ""}${
                tab.secondary ? " session-tab--secondary" : ""
              }`}
              aria-current={sessionTab === tab.id ? "page" : undefined}
              onClick={() => setSessionTab(tab.id)}
            >
              {tab.label}
              {tab.id === "warnings" && warningCount > 0 && (
                <span className="session-tab-badge">{warningCount}</span>
              )}
            </button>
          </span>
        ))}
      </nav>

      {importSuccess && (
        <div className="success-banner" role="status">
          <span>{importSuccess}</span>
          <button
            type="button"
            className="success-banner-dismiss"
            aria-label="Dismiss"
            onClick={() => setImportSuccess(null)}
          >
            ×
          </button>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}
      {importing && (
        <div className="import-overlay" role="alertdialog" aria-busy="true" aria-labelledby="import-overlay-title">
          <div className="import-overlay-card">
            <LoadingMark size={88} label="" />
            <h2 id="import-overlay-title">Importing timetable…</h2>
            <p>
              {importFileName ? `Processing ${importFileName}` : "This may take up to a minute for large files."}
            </p>
          </div>
        </div>
      )}
      {sessionTab === "timetable" && (
        <div className="tt-page tt-page--timetable">
          {loading && !grid && viewKind !== "block_overview" && (
            <LoadingMark label="Loading timetable…" />
          )}
          {!loading && courses.length === 0 && (
            <section className="card">
              <h2>No timetable data</h2>
              <p className="muted">
                Add staff, rooms, classes, and qualifications from their tabs, or import a desktop Timetable
                Export (.xlsm) / load demo data to begin.
              </p>
              <div className="row gap">
                <input
                  ref={importRef}
                  type="file"
                  accept=".xlsm,.xlsx"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void onImportFile("session", file);
                    e.target.value = "";
                  }}
                />
                <button type="button" className="btn-primary" onClick={() => importRef.current?.click()} disabled={importing}>
                  Import from desktop
                </button>
                <button type="button" className="btn-secondary" onClick={() => void onSeedDemo()} disabled={seeding}>
                  Load demo data
                </button>
              </div>
            </section>
          )}

          {courses.length > 0 && (
        <div className="tt-workspace">
          <TimetableSidebar
            mode={timetableMode}
            onModeChange={(m) => void onModeChange(m)}
            viewKind={viewKind}
            onViewKindChange={(k) => void onViewKindChange(k)}
            entities={sidebarEntities}
            selectedId={sidebarSelectedId}
            onSelect={(id) => void onSidebarSelect(id)}
            filter={sidebarFilter}
            onFilterChange={setSidebarFilter}
            reorderable={sidebarReorderable}
            onMoveUp={sidebarReorderable ? () => void onSidebarReorder(-1) : undefined}
            onMoveDown={sidebarReorderable ? () => void onSidebarReorder(1) : undefined}
            courseAdmin={courseAdmin}
            onCourseAdd={() => void onCourseAdd()}
            onCourseDuplicate={() => void onCourseDuplicate()}
            onCourseDelete={() => void onCourseDelete()}
            onCourseToggleLock={() => void onCourseToggleLock()}
            courseLocked={!!activeCourse?.timetable_locked}
            staffAdmin={staffAdmin}
            onStaffToggleLock={() => void onStaffToggleLock()}
            staffLocked={!!activeStaff?.timetable_locked}
          />
          <div className="tt-main">
            <div className="tt-main-primary">
            {viewKind === "course" && grid?.schedule_variants && grid.schedule_variants.length > 0 && (
              <ScheduleVariantBar
                variants={grid.schedule_variants}
                selectedPreviewWeek={previewSemesterWeek}
                onSelect={(w) => void onPreviewWeekChange(w)}
              />
            )}
            {viewKind === "course_semester" && (
              <CourseSemesterPanel
                schedule={semesterSchedule}
                loading={auxLoading}
                onSelectWeek={(w) => void onSemesterWeekSelect(w)}
                onToggleWeek={(bid, w) => void onToggleSemesterWeek(bid, w)}
              />
            )}
            {viewKind === "block_delivery" && (
              <BlockDeliveryPanel
                panel={blockPanel}
                loading={auxLoading}
                suggestedCode={suggestedBlockCode}
                onCourseChange={(id) => void onBlockCourseChange(id)}
                onBlockWeekChange={(idx) => void onBlockWeekChange(idx)}
                onStartWeekChange={(w) => void onBlockCoursePatch({ block_start_semester_week: w })}
                onBlockLengthChange={(w) => void onBlockCoursePatch({ block_week_count: w })}
                onDuplicateGroup={(code) => void onDuplicateBlockGroup(code)}
                onDeleteGroup={() => void onDeleteBlockGroup()}
              />
            )}
            {viewKind === "block_overview" ? (
              <BlockOverviewView
                overview={blockOverview}
                loading={loading || auxLoading}
                onLoadUsage={(cid, week) => api.blockWeekUsage(sessionId, cid, week).catch(() => null)}
              />
            ) : (
              grid && (
                <WeekGridView
                  grid={grid}
                  sessionId={sessionId}
                  viewKind={viewKind}
                  editable={editable}
                  zoom={gridZoom}
                  fitToViewport
                  showAlerts={showAlerts}
                  onMove={editable ? onMove : undefined}
                  onEdit={editable ? setEditBooking : undefined}
                  onCreateEmpty={
                    canCreateOnGrid
                      ? (day, startSlot, endSlot) => {
                          const cid = mutationCourseId();
                          if (cid == null) return;
                          setCreateDraft({ courseId: cid, day, startSlot, endSlot });
                        }
                      : undefined
                  }
                  onPlacePending={canPlacePending ? onPlacePending : undefined}
                  onToggleLock={editable ? onToggleLock : undefined}
                  onAlternateMove={editable ? onAlternateMove : undefined}
                  onDismissViolation={showAlerts ? onDismissViolation : undefined}
                  onSetClassColour={editable ? onSetClassColour : undefined}
                  onMergeClasses={editable ? onMergeClasses : undefined}
                  onUnmergeClasses={editable ? onUnmergeClasses : undefined}
                  onDeletePlacecard={editable ? onDeletePlacecard : undefined}
                  colourByClass={colourByClass}
                />
              )
            )}
            </div>
            {showsHoldingArea(viewKind) && (
              <HoldingAreaPanel
                items={holding}
                loading={holdingLoading}
                acceptBookingDrop={editable}
                onBookingDrop={editable ? (id) => void onReturnToHolding(id) : undefined}
                sticky
              />
            )}
            {grid && showAlerts && grid.violations.length > 0 && (
              <TimetableViolationsPanel
                violations={grid.violations}
                onViewAll={() => setSessionTab("warnings")}
              />
            )}
          </div>
        </div>
          )}
        </div>
      )}

      {sessionTab === "staff" && (
        <div className="tt-page tt-page--entity">
          <EntityEditorsPanel
            sessionId={sessionId}
            staff={staff}
            rooms={rooms}
            units={units}
            courses={courses}
            qualifications={qualifications}
            onUpdated={onEntityUpdated}
            fixedTab="staff"
            showLinkedImport={globalLink?.linked === true}
            syncToken={entitySyncToken}
          />
        </div>
      )}
      {sessionTab === "lecturer_cover" && (
        <div className="tt-page tt-page--cover">
          <LecturerCoverPanel
            sessionId={sessionId}
            staff={staff}
            onError={setError}
            syncToken={entitySyncToken}
            globalSessionId={
              globalLink?.linked ? globalLink.global_session_id ?? null : null
            }
          />
        </div>
      )}
      {sessionTab === "rooms" && (
        <div className="tt-page tt-page--entity">
          <EntityEditorsPanel
            sessionId={sessionId}
            staff={staff}
            rooms={rooms}
            units={units}
            courses={courses}
            qualifications={qualifications}
            onUpdated={onEntityUpdated}
            fixedTab="rooms"
          />
        </div>
      )}
      {sessionTab === "units" && (
        <div className="tt-page tt-page--entity">
          <EntityEditorsPanel
            sessionId={sessionId}
            staff={staff}
            rooms={rooms}
            units={units}
            courses={courses}
            qualifications={qualifications}
            onUpdated={onEntityUpdated}
            fixedTab="units"
            focusEntityId={focusUnitId}
            onFocusConsumed={() => setFocusUnitId(null)}
          />
        </div>
      )}
      {sessionTab === "qualifications" && (
        <div className="tt-page tt-page--entity">
          <EntityEditorsPanel
            sessionId={sessionId}
            staff={staff}
            rooms={rooms}
            units={units}
            courses={courses}
            qualifications={qualifications}
            onUpdated={onEntityUpdated}
            fixedTab="qualifications"
            onNavigateToUnit={(unitId) => {
              setFocusUnitId(unitId);
              setSessionTab("units");
            }}
            showLinkedImport={globalLink?.linked === true}
          />
        </div>
      )}
      {sessionTab === "changelog" && courses.length > 0 && (
        <ChangeLogPanel
          sessionId={sessionId}
          resolveCourseId={resolveCourseId}
          refreshKey={changeLogKey}
          onRollback={() => {
            setChangeLogKey((k) => k + 1);
            void reloadView();
            notifyPeers();
          }}
        />
      )}
      {sessionTab === "warnings" && courses.length > 0 && (
        <ViolationsReportPanel
          sessionId={sessionId}
          refreshKey={changeLogKey}
          onGoToBooking={goToWarningBooking}
        />
      )}
      {sessionTab === "clash_settings" && courses.length > 0 && (
        <ClashSettingsPanel
          sessionId={sessionId}
          onUpdated={(opts) => {
            void loadCurrentView(sessionId, viewState(), {
              colourByClass: colourByClassRef.current,
              clashDetect:
                opts?.clashDetect ??
                clashDetectForPrefs({ autoClashDetect: autoClashDetectRef.current }),
            });
            setChangeLogKey((k) => k + 1);
          }}
          onCombinedClassesReapplied={async () => {
            await loadCurrentView(sessionId, viewState(), {
              colourByClass: colourByClassRef.current,
              clashDetect: "once",
            });
            notifyPeers();
            setSessionTab("timetable");
            setChangeLogKey((k) => k + 1);
          }}
        />
      )}
      {sessionTab === "custodians" && courses.length > 0 && (
        <ClassCustodiansPanel sessionId={sessionId} refreshKey={changeLogKey} />
      )}
      {sessionTab === "usage" && courses.length > 0 && (
        <UsageDashboard sessionId={sessionId} refreshKey={changeLogKey} />
      )}
      {sessionTab === "lap" && courses.length > 0 && (
        <LapCreationPanel sessionId={sessionId} refreshKey={changeLogKey} />
      )}

      {createDraft && grid && (
        <BookingCreateDialog
          grid={grid}
          courseId={createDraft.courseId}
          day={createDraft.day}
          startSlot={createDraft.startSlot}
          endSlot={createDraft.endSlot}
          units={units}
          staff={staff}
          rooms={rooms}
          saving={mutating}
          onClose={() => setCreateDraft(null)}
          onCreate={onCreateBooking}
        />
      )}
      {editBooking && grid && (
        <BookingEditDialog
          booking={editBooking}
          grid={grid}
          staff={staff}
          rooms={rooms}
          saving={mutating}
          onClose={() => setEditBooking(null)}
          onSave={onSaveEdit}
        />
      )}
      {dialogs}
    </AppShell>
  );
}
