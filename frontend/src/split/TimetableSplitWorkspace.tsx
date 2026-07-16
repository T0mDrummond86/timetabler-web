import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Course, Room, Staff, TimetableGlobalLink } from "../api";
import type { BookingCard, BookingChange, TimetableEntity, TimetableGrid } from "../types";
import { BlockDeliveryPanel } from "../components/BlockDeliveryPanel";
import { BookingEditDialog } from "../components/BookingEditDialog";
import { TimetableSidebar } from "../components/TimetableSidebar";
import type { TimetableMode, ViewKind } from "../viewKinds";
import {
  defaultViewKindForMode,
  entityListViewKind,
  viewKindMode,
  COURSE_VIEW_KINDS,
} from "../viewKinds";
import { SplitPane } from "./SplitPane";
import {
  FOUR_WAY_PANE_ORDER,
  initialSlots,
  paneCount,
  SPLIT_PANE_LABELS,
  type SlotPaneState,
  type SplitLayoutKind,
} from "./splitLayout";
import { applySidebarSelect, patchSlotViewKind, slotSelectedId } from "./slotState";
import {
  DEFAULT_GRID_ZOOM,
  displayZoomPercent,
  resetGridZoom,
  zoomIn,
  zoomOut,
} from "../lib/gridZoom";
import { notifySessionChanged, useSessionSync } from "../lib/sessionSync";
import { markGlobalSessionDirty } from "../lib/globalSessionRefresh";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";

import { readDisplayPrefs } from "../lib/displayPrefs";

const COURSE_VIEWS = COURSE_VIEW_KINDS;
const SEMESTER_WEEKS = 52;

async function defaultIdsForView(
  sessionId: number,
  kind: ViewKind,
): Promise<Partial<SlotPaneState>> {
  const rows = await api.timetableEntities(sessionId, entityListViewKind(kind));
  if (!rows.length) return {};
  const id = rows[0].id;
  if (kind === "block_delivery") return { qualificationId: id, blockCourseId: null };
  if (COURSE_VIEWS.includes(kind)) return { courseId: id };
  if (kind === "staff") return { staffId: id };
  if (kind === "day" || kind === "room") return { roomDay: id };
  return {};
}

type Props = {
  sessionId: number;
  layout: SplitLayoutKind;
};

type UndoEntry = { change: BookingChange; courseId: number };

export function TimetableSplitWorkspace({ sessionId, layout }: Props) {
  const count = paneCount(layout);
  const labels = SPLIT_PANE_LABELS[layout];
  const paneIndices = useMemo(
    () =>
      layout === "4"
        ? [...FOUR_WAY_PANE_ORDER]
        : Array.from({ length: count }, (_, i) => i),
    [layout, count],
  );

  const [slots, setSlots] = useState<SlotPaneState[]>(() => initialSlots(layout));
  const [activeIndex, setActiveIndex] = useState(0);
  const [refreshTokens, setRefreshTokens] = useState<number[]>(() => Array(count).fill(0));
  const [mode, setMode] = useState<TimetableMode>("regular");
  const [sidebarEntities, setSidebarEntities] = useState<TimetableEntity[]>([]);
  const [sidebarFilter, setSidebarFilter] = useState("");
  const [gridZoom, setGridZoom] = useState(DEFAULT_GRID_ZOOM);
  const [{ colourByClass, showAlerts, autoClashDetect }] = useState(readDisplayPrefs);
  const [blockPanel, setBlockPanel] = useState<Awaited<ReturnType<typeof api.blockDeliveryPanel>> | null>(
    null,
  );
  const [suggestedBlockCode, setSuggestedBlockCode] = useState<string | null>(null);
  const [auxLoading, setAuxLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editBooking, setEditBooking] = useState<BookingCard | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [mutating, setMutating] = useState(false);
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const [redoStack, setRedoStack] = useState<UndoEntry[]>([]);
  const [globalLink, setGlobalLink] = useState<TimetableGlobalLink | null>(null);
  const globalLinkRef = useRef(globalLink);
  globalLinkRef.current = globalLink;
  const { dialogs } = useConfirmPrompt();

  const notifyLinked = useCallback(() => {
    notifySessionChanged(sessionId);
  }, [sessionId]);

  useEffect(() => {
    void api.timetableGlobalLink(sessionId).then(setGlobalLink).catch(() => setGlobalLink(null));
  }, [sessionId]);

  useEffect(() => {
    return () => {
      const link = globalLinkRef.current;
      if (link?.linked && link.global_session_id) {
        markGlobalSessionDirty(link.global_session_id);
      }
    };
  }, [sessionId]);

  const syncingRef = useRef(false);
  const gridsRef = useRef<(TimetableGrid | null)[]>(Array(count).fill(null));
  const slotsRef = useRef(slots);
  slotsRef.current = slots;

  const activeSlot = slots[activeIndex] ?? slots[0];

  const bumpRefresh = useCallback((idx?: number) => {
    setRefreshTokens((prev) => {
      if (idx === undefined) return prev.map((t) => t + 1);
      const next = [...prev];
      if (idx >= 0 && idx < next.length) next[idx] = next[idx] + 1;
      return next;
    });
  }, []);

  const loadSidebarEntities = useCallback(async (kind: ViewKind) => {
    const rows = await api.timetableEntities(sessionId, entityListViewKind(kind));
    setSidebarEntities(rows);
    return rows;
  }, [sessionId]);

  const loadBlockPanel = useCallback(
    async (slot: SlotPaneState) => {
      if (slot.viewKind !== "block_delivery" || !slot.qualificationId) {
        setBlockPanel(null);
        return;
      }
      setAuxLoading(true);
      try {
        const panel = await api.blockDeliveryPanel(sessionId, {
          qualificationId: slot.qualificationId,
          courseId: slot.blockCourseId,
          blockWeekIndex: slot.blockWeekIndex,
        });
        setBlockPanel(panel);
        const sug = await api.suggestedBlockCode(sessionId, slot.qualificationId);
        setSuggestedBlockCode(sug.code);
        if (
          panel.selected_course_id &&
          panel.selected_course_id !== slot.blockCourseId
        ) {
          setSlots((prev) => {
            const next = [...prev];
            const idx = next.findIndex(
              (s) => s.viewKind === "block_delivery" && s.qualificationId === slot.qualificationId,
            );
            if (idx < 0 || next[idx].blockCourseId === panel.selected_course_id) return prev;
            next[idx] = {
              ...next[idx],
              blockCourseId: panel.selected_course_id,
              blockWeekIndex: panel.block_week_index,
            };
            return next;
          });
          bumpRefresh(
            slotsRef.current.findIndex(
              (s) => s.viewKind === "block_delivery" && s.qualificationId === slot.qualificationId,
            ),
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Block panel failed");
      } finally {
        setAuxLoading(false);
      }
    },
    [sessionId, bumpRefresh],
  );

  const onGroupRenamed = useCallback(
    (_updated: Course) => {
      bumpRefresh();
      notifyLinked();
      const slot = slotsRef.current[activeIndex] ?? slotsRef.current[0];
      if (slot?.viewKind === "block_delivery" && slot.qualificationId) {
        void loadBlockPanel(slot);
      }
      if (slot) void loadSidebarEntities(slot.viewKind);
    },
    [notifyLinked, bumpRefresh, activeIndex, loadBlockPanel, loadSidebarEntities],
  );

  useSessionSync(sessionId, () => {
    bumpRefresh();
    const slot = slotsRef.current[activeIndex] ?? slotsRef.current[0];
    if (slot) void loadSidebarEntities(slot.viewKind);
    if (slot?.viewKind === "block_delivery" && slot.qualificationId) {
      void loadBlockPanel(slot);
    }
  });

  const initAllSlots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const base = initialSlots(layout);
      const enriched = await Promise.all(
        base.map(async (slot) => ({
          ...slot,
          ...(await defaultIdsForView(sessionId, slot.viewKind)),
        })),
      );
      setSlots(enriched);
      setRefreshTokens(Array(count).fill(1));
      setUndoStack([]);
      setRedoStack([]);
      const [staffList, roomList] = await Promise.all([api.staff(sessionId), api.rooms(sessionId)]);
      setStaff(staffList);
      setRooms(roomList);
      setActiveIndex(0);
      const first = enriched[0];
      syncingRef.current = true;
      setMode(viewKindMode(first.viewKind));
      await loadSidebarEntities(first.viewKind);
      if (first.viewKind === "block_delivery") await loadBlockPanel(first);
      syncingRef.current = false;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load split view");
    } finally {
      setLoading(false);
    }
  }, [sessionId, layout, count, labels, loadSidebarEntities, loadBlockPanel]);

  useEffect(() => {
    void initAllSlots();
  }, [initAllSlots]);

  const syncSidebarFromSlot = useCallback(
    async (slot: SlotPaneState, index: number) => {
      syncingRef.current = true;
      setMode(viewKindMode(slot.viewKind));
      await loadSidebarEntities(slot.viewKind);
      if (slot.viewKind === "block_delivery") {
        await loadBlockPanel(slot);
      } else {
        setBlockPanel(null);
      }
      syncingRef.current = false;
      setActiveIndex(index);
    },
    [loadSidebarEntities, loadBlockPanel],
  );

  function activateSlot(index: number) {
    if (index === activeIndex) return;
    const slot = slotsRef.current[index];
    if (!slot) return;
    setSidebarFilter("");
    void syncSidebarFromSlot(slot, index);
  }

  function updateActiveSlot(patch: Partial<SlotPaneState>) {
    setSlots((prev) => {
      const next = [...prev];
      next[activeIndex] = { ...next[activeIndex], ...patch };
      return next;
    });
    bumpRefresh(activeIndex);
  }

  async function onModeChange(nextMode: TimetableMode) {
    if (syncingRef.current) return;
    setSidebarFilter("");
    setMode(nextMode);
    const kind = defaultViewKindForMode(nextMode);
    syncingRef.current = true;
    const rows = await loadSidebarEntities(kind);
    syncingRef.current = false;
    const patch: Partial<SlotPaneState> = { ...patchSlotViewKind(activeSlot, kind) };
    if (kind === "block_delivery" && rows.length) patch.qualificationId = rows[0].id;
    if (COURSE_VIEWS.includes(kind) && rows.length) patch.courseId = rows[0].id;
    if (kind === "staff" && rows.length) patch.staffId = rows[0].id;
    updateActiveSlot(patch);
    if (kind === "block_delivery") {
      const merged = { ...activeSlot, ...patch };
      void loadBlockPanel(merged as SlotPaneState);
    }
  }

  async function onViewKindChange(kind: ViewKind) {
    if (syncingRef.current) return;
    setSidebarFilter("");
    setMode(viewKindMode(kind));
    syncingRef.current = true;
    const rows = await loadSidebarEntities(kind);
    syncingRef.current = false;
    let patch = patchSlotViewKind(activeSlot, kind);
    if (kind === "block_delivery" && rows.length) {
      patch = { ...patch, qualificationId: rows[0].id };
    }
    if (COURSE_VIEWS.includes(kind) && rows.length) {
      patch = { ...patch, courseId: rows[0].id };
    }
    if (kind === "staff" && rows.length) patch = { ...patch, staffId: rows[0].id };
    updateActiveSlot(patch);
    if (kind === "block_delivery") {
      void loadBlockPanel({ ...activeSlot, ...patch });
    } else {
      setBlockPanel(null);
    }
  }

  function onSidebarSelect(id: number) {
    if (syncingRef.current) return;
    const next = applySidebarSelect(activeSlot, id);
    setSlots((prev) => {
      const copy = [...prev];
      copy[activeIndex] = next;
      return copy;
    });
    bumpRefresh(activeIndex);
  }

  function onSemesterWeekChange(week: number) {
    updateActiveSlot({ semesterWeek: week });
  }

  function onBlockCourseChange(id: number) {
    updateActiveSlot({ blockCourseId: id });
    void loadBlockPanel({ ...activeSlot, blockCourseId: id });
  }

  function onBlockWeekChange(idx: number) {
    updateActiveSlot({ blockWeekIndex: idx });
  }

  const handleGridLoaded = useCallback((index: number, grid: TimetableGrid | null) => {
    gridsRef.current[index] = grid;
  }, []);

  const gridLoadedHandlers = useMemo(
    () =>
      paneIndices.map(
        (slotIdx) => (grid: TimetableGrid | null) => handleGridLoaded(slotIdx, grid),
      ),
    [paneIndices, handleGridLoaded],
  );

  const mutationCourseId = useCallback(
    (booking?: BookingCard | null) => {
      if (booking?.course_id) return booking.course_id;
      const slot = slotsRef.current[activeIndex];
      if (slot.viewKind === "block_delivery") return slot.blockCourseId;
      if (COURSE_VIEWS.includes(slot.viewKind)) return slot.courseId;
      return null;
    },
    [activeIndex],
  );

  async function afterMutation() {
    bumpRefresh();
    notifyLinked();
  }

  const pushUndo = useCallback((change: BookingChange, courseId: number) => {
    setUndoStack((prev) => [...prev, { change, courseId }]);
    setRedoStack([]);
  }, []);

  async function undo() {
    if (!undoStack.length || mutating) return;
    const entry = undoStack[undoStack.length - 1];
    setMutating(true);
    setError(null);
    try {
      await api.restoreBookings(sessionId, {
        course_id: entry.courseId,
        action: "undo",
        label: entry.change.description,
        snapshots: entry.change.before,
      });
      setUndoStack((prev) => prev.slice(0, -1));
      setRedoStack((prev) => [...prev, entry]);
      bumpRefresh();
      notifyLinked();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo failed");
    } finally {
      setMutating(false);
    }
  }

  async function redo() {
    if (!redoStack.length || mutating) return;
    const entry = redoStack[redoStack.length - 1];
    setMutating(true);
    setError(null);
    try {
      await api.restoreBookings(sessionId, {
        course_id: entry.courseId,
        action: "redo",
        label: entry.change.description,
        snapshots: entry.change.after,
      });
      setRedoStack((prev) => prev.slice(0, -1));
      setUndoStack((prev) => [...prev, entry]);
      bumpRefresh();
      notifyLinked();
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

  async function onMove(bookingId: number, column: number, startSlot: number) {
    const grid = gridsRef.current[activeIndex];
    const booking = grid?.bookings.find((b) => b.id === bookingId);
    const cid = mutationCourseId(booking);
    if (!cid || !grid) return;
    try {
      if (grid.column_kind === "room") {
        const room = rooms[column];
        if (!room) return;
        const result = await api.moveBooking(sessionId, bookingId, {
          course_id: cid,
          day: grid.focus_day ?? activeSlot.roomDay,
          start_slot: startSlot,
          room_id: room.id,
        });
        pushUndo(result.change, cid);
      } else {
        const result = await api.moveBooking(sessionId, bookingId, {
          course_id: cid,
          day: column,
          start_slot: startSlot,
        });
        pushUndo(result.change, cid);
      }
      await afterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move failed");
    }
  }

  async function onSetClassColour(unitId: number, fill: string | null) {
    setMutating(true);
    setError(null);
    try {
      await api.patchUnit(sessionId, unitId, { screen_fill_colour: fill });
      await afterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Class colour update failed");
    } finally {
      setMutating(false);
    }
  }

  async function onDismissViolation(bookingId: number, code: string) {
    try {
      await api.dismissViolation(sessionId, bookingId, code);
      bumpRefresh(activeIndex);
      notifyLinked();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dismiss failed");
    }
  }

  async function onMergeClasses(bookingIds: number[]) {
    setMutating(true);
    setError(null);
    try {
      await api.mergeClasses(sessionId, bookingIds);
      await afterMutation();
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
      await afterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unmerge failed");
    } finally {
      setMutating(false);
    }
  }

  async function onLogManualChange(booking: BookingCard) {
    setError(null);
    try {
      await api.createManualChangeLog(sessionId, booking.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record manual change");
    }
  }

  const gridClass =
    layout === "4"
      ? "split-grid split-grid-4"
      : layout === "2v"
        ? "split-grid split-grid-2v"
        : "split-grid split-grid-2h";

  const sidebarSelectedId = slotSelectedId(activeSlot);

  const viewExtras = (
    <>
      {activeSlot.viewKind === "course_semester" && (
        <div className="tt-sidebar-section">
          <span className="tt-sidebar-label">Semester week</span>
          <input
            type="number"
            className="field-input"
            min={1}
            max={SEMESTER_WEEKS}
            value={activeSlot.semesterWeek}
            onChange={(e) => onSemesterWeekChange(Number(e.target.value) || 1)}
            aria-label="Semester week"
          />
        </div>
      )}
      {activeSlot.viewKind === "block_delivery" && (
        <BlockDeliveryPanel
          embedded
          panel={blockPanel}
          loading={auxLoading}
          suggestedCode={suggestedBlockCode}
          onCourseChange={onBlockCourseChange}
          onBlockWeekChange={onBlockWeekChange}
          onStartWeekChange={(w) => {
            if (!activeSlot.blockCourseId) return;
            void api
              .patchCourse(sessionId, activeSlot.blockCourseId, { block_start_semester_week: w })
              .then(() => {
                void loadBlockPanel(activeSlot);
                bumpRefresh(activeIndex);
                notifyLinked();
              });
          }}
          onBlockLengthChange={(w) => {
            if (!activeSlot.blockCourseId) return;
            void api
              .patchCourse(sessionId, activeSlot.blockCourseId, { block_week_count: w })
              .then(() => {
                void loadBlockPanel(activeSlot);
                bumpRefresh(activeIndex);
                notifyLinked();
              });
          }}
        />
      )}
    </>
  );

  return (
    <div className="split-workspace">
      <TimetableSidebar
        header={
          <p className="split-active-hint">
            Click a grid to edit it · active: {labels[activeIndex]}
          </p>
        }
        viewExtras={viewExtras}
        mode={mode}
        onModeChange={(m) => void onModeChange(m)}
        viewKind={activeSlot.viewKind}
        onViewKindChange={(k) => void onViewKindChange(k)}
        entities={sidebarEntities}
        selectedId={sidebarSelectedId}
        onSelect={onSidebarSelect}
        filter={sidebarFilter}
        onFilterChange={setSidebarFilter}
      />

      <div className="split-main">
        <div className="split-zoom-bar">
          <span className="tt-toolbar-label">Zoom</span>
          <button
            type="button"
            className="btn-secondary btn-xs"
            onClick={() => setGridZoom((z) => zoomOut(z))}
            aria-label="Zoom out"
          >
            −
          </button>
          <span className="tt-zoom-label">{displayZoomPercent(gridZoom)}%</span>
          <button
            type="button"
            className="btn-secondary btn-xs"
            onClick={() => setGridZoom((z) => zoomIn(z))}
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            type="button"
            className="btn-secondary btn-xs"
            onClick={() => setGridZoom(resetGridZoom())}
          >
            100%
          </button>
          <button type="button" className="btn-secondary btn-xs" onClick={() => bumpRefresh()}>
            Reload all
          </button>
          <span className="tt-toolbar-sep" aria-hidden />
          <button
            type="button"
            className="btn-secondary btn-xs"
            onClick={() => void undo()}
            disabled={!undoStack.length || mutating}
            title="Undo placecard change (⌘Z)"
          >
            Undo
          </button>
          <button
            type="button"
            className="btn-secondary btn-xs"
            onClick={() => void redo()}
            disabled={!redoStack.length || mutating}
            title="Redo placecard change (⌘⇧Z)"
          >
            Redo
          </button>
        </div>

        {error && <p className="error-banner">{error}</p>}
        {loading && <p className="muted split-loading">Loading split view…</p>}

        <div className={gridClass}>
          {paneIndices.map((slotIdx, panePos) => (
            <div key={slotIdx} className="split-pane-wrap">
              <SplitPane
                sessionId={sessionId}
                slot={slots[slotIdx] ?? initialSlots(layout)[slotIdx]}
                isActive={slotIdx === activeIndex}
                colourByClass={colourByClass}
                showAlerts={showAlerts}
                autoClashDetect={autoClashDetect}
                gridZoom={gridZoom}
                onActivate={() => activateSlot(slotIdx)}
                refreshToken={refreshTokens[slotIdx] ?? 0}
                onGridLoaded={gridLoadedHandlers[panePos]}
                onMove={onMove}
                onEdit={setEditBooking}
                onDismissViolation={onDismissViolation}
                onSetClassColour={onSetClassColour}
                onMergeClasses={onMergeClasses}
                onUnmergeClasses={onUnmergeClasses}
                onLogManualChange={onLogManualChange}
                onGroupRenamed={onGroupRenamed}
                onRenameError={setError}
              />
            </div>
          ))}
        </div>
      </div>

      {editBooking && gridsRef.current[activeIndex] && (
        <BookingEditDialog
          booking={editBooking}
          grid={gridsRef.current[activeIndex]!}
          staff={staff}
          rooms={rooms}
          saving={mutating}
          onClose={() => setEditBooking(null)}
          onSave={async (patch) => {
            const cid = mutationCourseId(editBooking);
            if (!cid) return;
            setMutating(true);
            try {
              const result = await api.patchBooking(sessionId, editBooking.id, {
                course_id: cid,
                ...patch,
              });
              pushUndo(result.change, cid);
              setEditBooking(null);
              await afterMutation();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Save failed");
            } finally {
              setMutating(false);
            }
          }}
        />
      )}
      {dialogs}
    </div>
  );
}
