import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CalendarWeek, type CoverCandidate, type CoverRequest, type Staff } from "../api";
import type { BookingCard, TimetableGrid } from "../types";
import { WeekGridView } from "./WeekGridView";
import { LoadingMark } from "./LoadingMark";
import { DEFAULT_GRID_ZOOM, displayZoomPercent, resetGridZoom, zoomIn, zoomOut } from "../lib/gridZoom";
import { readDisplayPrefs } from "../lib/displayPrefs";
import { copyCoverTimetable } from "../lib/coverTimetableClipboard";
import { slotRangeLabel } from "../lib/timeUtils";

type Props = {
  sessionId: number;
  staff: Staff[];
  onError?: (message: string) => void;
  syncToken?: number;
  /** Global session this timetable belongs to; null if not linked. */
  globalSessionId: number | null;
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Add whole days to an ISO date string (date-only, no timezone drift). */
function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return dt.toISOString().slice(0, 10);
}

export function LecturerCoverPanel({
  sessionId,
  staff,
  onError,
  syncToken = 0,
  globalSessionId,
}: Props) {
  const [{ colourByClass, showAlerts }] = useState(readDisplayPrefs);
  const [needingCoverStaffId, setNeedingCoverStaffId] = useState<number | null>(null);
  const [coverStaffId, setCoverStaffId] = useState<number | null>(null);
  const [coverCandidates, setCoverCandidates] = useState<CoverCandidate[]>([]);
  const [selectedBookingId, setSelectedBookingId] = useState<number | null>(null);
  const [leftGrid, setLeftGrid] = useState<TimetableGrid | null>(null);
  const [rightGrid, setRightGrid] = useState<TimetableGrid | null>(null);
  const [leftLoading, setLeftLoading] = useState(false);
  const [rightLoading, setRightLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [gridZoom, setGridZoom] = useState(DEFAULT_GRID_ZOOM);
  // Pending cover requests persist on the server (session-scoped) so they
  // survive the email round-trip and stay editable until pushed to the log.
  const [requests, setRequests] = useState<CoverRequest[]>([]);
  const [busyRequestId, setBusyRequestId] = useState<number | null>(null);
  const [coverDate, setCoverDate] = useState(todayIso);
  const [calendar, setCalendar] = useState<CalendarWeek[]>([]);
  const [coverSemester, setCoverSemester] = useState(1);
  const [coverWeek, setCoverWeek] = useState(1);

  const selectedBooking = useMemo(
    () => leftGrid?.bookings.find((b) => b.id === selectedBookingId) ?? null,
    [leftGrid, selectedBookingId],
  );

  // The left grid is a single repeating-week template, so it can badge only one
  // cover per class. When a calendar is loaded, scope to the week currently in
  // focus (semester + week) so per-week covers for the same class don't collide;
  // without a calendar, fall back to one request per class.
  const requestByBooking = useMemo(() => {
    const hasCal = calendar.length > 0;
    const m = new Map<number, CoverRequest>();
    for (const r of requests) {
      if (r.booking_id == null) continue;
      if (hasCal && (r.semester !== coverSemester || r.week_number !== coverWeek)) continue;
      m.set(r.booking_id, r);
    }
    return m;
  }, [requests, calendar, coverSemester, coverWeek]);

  const hasCalendar = calendar.length > 0;
  const semesters = useMemo(
    () => [...new Set(calendar.map((w) => w.semester))].sort((a, b) => a - b),
    [calendar],
  );
  const weeksForSemester = useMemo(
    () =>
      calendar
        .filter((w) => w.semester === coverSemester)
        .sort((a, b) => a.week_number - b.week_number),
    [calendar, coverSemester],
  );

  // Resolve the cover date for a booking from semester+week + the booking's weekday.
  const computedDateFor = useCallback(
    (booking: BookingCard): string => {
      const wk = calendar.find(
        (w) => w.semester === coverSemester && w.week_number === coverWeek,
      );
      if (!wk?.monday_date) return "";
      return addDays(wk.monday_date, booking.day); // booking.day: 0 = Monday
    },
    [calendar, coverSemester, coverWeek],
  );

  // Left grid badged with this session's pending cover requests (and clipboard).
  const displayLeftGrid = useMemo<TimetableGrid | null>(() => {
    if (!leftGrid) return null;
    if (requestByBooking.size === 0) return leftGrid;
    return {
      ...leftGrid,
      bookings: leftGrid.bookings.map((b) => {
        const req = requestByBooking.get(b.id);
        return req
          ? { ...b, cover_staff_id: req.cover_staff_id, cover_staff_name: req.cover_staff_name }
          : b;
      }),
    };
  }, [leftGrid, requestByBooking]);

  const loadRequests = useCallback(async () => {
    try {
      const data = await api.coverRequests(sessionId);
      setRequests(data.requests);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to load cover requests");
    }
  }, [sessionId, onError]);

  const loadLeftGrid = useCallback(async () => {
    if (needingCoverStaffId == null) {
      setLeftGrid(null);
      return;
    }
    setLeftLoading(true);
    try {
      const grid = await api.timetable(sessionId, {
        view: "staff",
        staffId: needingCoverStaffId,
        colourByClass,
        hideDismissed: true,
      });
      setLeftGrid(grid);
    } catch (err) {
      setLeftGrid(null);
      onError?.(err instanceof Error ? err.message : "Failed to load timetable");
    } finally {
      setLeftLoading(false);
    }
  }, [sessionId, needingCoverStaffId, colourByClass, onError]);

  const loadRightGrid = useCallback(async () => {
    if (coverStaffId == null) {
      setRightGrid(null);
      return;
    }
    setRightLoading(true);
    try {
      const grid = await api.timetable(sessionId, {
        view: "staff",
        staffId: coverStaffId,
        colourByClass,
        hideDismissed: true,
      });
      setRightGrid(grid);
    } catch (err) {
      setRightGrid(null);
      onError?.(err instanceof Error ? err.message : "Failed to load cover timetable");
    } finally {
      setRightLoading(false);
    }
  }, [sessionId, coverStaffId, colourByClass, onError]);

  // Pending requests are session-wide — load once per session.
  useEffect(() => {
    void loadRequests();
  }, [loadRequests, syncToken]);

  // Load the global session's academic calendar (for semester+week → date).
  useEffect(() => {
    if (globalSessionId == null) {
      setCalendar([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.calendar(globalSessionId);
        if (!cancelled) setCalendar(data.weeks);
      } catch {
        if (!cancelled) setCalendar([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [globalSessionId, syncToken]);

  // Keep semester/week selections valid against the loaded calendar.
  useEffect(() => {
    if (semesters.length && !semesters.includes(coverSemester)) {
      setCoverSemester(semesters[0]);
    }
  }, [semesters, coverSemester]);

  // Sync the create-time cover date for the selected booking.
  useEffect(() => {
    if (!selectedBooking) return;
    const existing = requestByBooking.get(selectedBooking.id);
    if (existing?.cover_date) {
      setCoverDate(existing.cover_date);
      return;
    }
    const computed = computedDateFor(selectedBooking);
    if (computed) setCoverDate(computed);
  }, [selectedBooking, coverSemester, coverWeek, computedDateFor, requestByBooking]);

  useEffect(() => {
    setSelectedBookingId(null);
    setCoverStaffId(null);
    setCoverCandidates([]);
    void loadLeftGrid();
  }, [needingCoverStaffId, loadLeftGrid, syncToken]);

  useEffect(() => {
    void loadRightGrid();
  }, [coverStaffId, loadRightGrid, syncToken]);

  useEffect(() => {
    if (selectedBookingId == null) {
      setCoverCandidates([]);
      setCoverStaffId(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.coverCandidates(sessionId, selectedBookingId);
        if (cancelled) return;
        setCoverCandidates(data.candidates);
        setCoverStaffId((prev) =>
          prev != null && data.candidates.some((c) => c.id === prev) ? prev : null,
        );
      } catch (err) {
        if (!cancelled) {
          setCoverCandidates([]);
          setCoverStaffId(null);
          onError?.(err instanceof Error ? err.message : "Failed to load cover lecturers");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, selectedBookingId, onError]);

  // Create (or update) a persisted cover request for the assigned class.
  async function assignCover(booking: BookingCard) {
    if (coverStaffId == null) {
      onError?.("Select a cover lecturer first");
      return;
    }
    if (!leftGrid) return;
    const coverName = staff.find((s) => s.id === coverStaffId)?.name ?? "";
    const awayName =
      staff.find((s) => s.id === needingCoverStaffId)?.name ?? leftGrid.entity_label;
    try {
      await api.createCoverRequest(sessionId, {
        booking_id: booking.id,
        cover_date: coverDate || null,
        semester: hasCalendar ? coverSemester : null,
        week_number: hasCalendar ? coverWeek : null,
        day_label: leftGrid.days[booking.day] ?? "",
        time_label: slotRangeLabel(booking.start_slot, booking.end_slot),
        group_name: booking.course_code ?? "",
        unit_name: booking.unit_name ?? booking.course_code ?? "",
        room_code: booking.room_code ?? "",
        away_staff_name: awayName,
        cover_staff_id: coverStaffId,
        cover_staff_name: coverName,
      });
      await loadRequests();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to create cover request");
    }
  }

  async function changeRequestCover(request: CoverRequest, staffId: number | null) {
    const name = staffId == null ? "" : staff.find((s) => s.id === staffId)?.name ?? "";
    setBusyRequestId(request.id);
    try {
      await api.updateCoverRequest(sessionId, request.id, {
        cover_staff_id: staffId,
        cover_staff_name: name,
      });
      await loadRequests();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to update cover request");
    } finally {
      setBusyRequestId(null);
    }
  }

  async function changeRequestDate(request: CoverRequest, date: string) {
    setBusyRequestId(request.id);
    try {
      await api.updateCoverRequest(sessionId, request.id, { cover_date: date || null });
      await loadRequests();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to update cover date");
    } finally {
      setBusyRequestId(null);
    }
  }

  async function deleteRequest(request: CoverRequest) {
    setBusyRequestId(request.id);
    try {
      await api.deleteCoverRequest(sessionId, request.id);
      await loadRequests();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to delete cover request");
    } finally {
      setBusyRequestId(null);
    }
  }

  async function pushRequestToLog(request: CoverRequest) {
    setBusyRequestId(request.id);
    try {
      await api.promoteCoverRequest(sessionId, request.id);
      await loadRequests();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to push to global log");
    } finally {
      setBusyRequestId(null);
    }
  }

  async function copyTimetableToClipboard() {
    if (!displayLeftGrid) return;
    const awayName =
      staff.find((s) => s.id === needingCoverStaffId)?.name ?? displayLeftGrid.entity_label;
    const title = `Cover timetable — ${awayName}`;
    // Match the grid badges: only the week in focus (requestByBooking is scoped).
    const dateByBookingId = new Map<number, string>();
    for (const [bid, r] of requestByBooking) {
      if (r.cover_date) dateByBookingId.set(bid, r.cover_date);
    }
    try {
      await copyCoverTimetable(displayLeftGrid, title, dateByBookingId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Copy failed");
    }
  }

  return (
    <div className="lecturer-cover-panel">
      <div className="lecturer-cover-toolbar">
        <div className="lecturer-cover-toolbar-group">
          <span className="lecturer-cover-toolbar-label">Lecturer requiring cover</span>
          <select
            className="field-select lecturer-cover-select"
            value={needingCoverStaffId ?? ""}
            onChange={(e) =>
              setNeedingCoverStaffId(e.target.value === "" ? null : Number(e.target.value))
            }
            aria-label="Lecturer requiring cover"
          >
            <option value="">Select lecturer…</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        {selectedBooking && (
          <div className="lecturer-cover-toolbar-group">
            <span className="lecturer-cover-toolbar-label">Cover lecturer</span>
            <select
              className="field-select lecturer-cover-select"
              value={coverStaffId ?? ""}
              onChange={(e) =>
                setCoverStaffId(e.target.value === "" ? null : Number(e.target.value))
              }
              aria-label="Cover lecturer"
            >
              <option value="">
                {coverCandidates.length ? "Select cover lecturer…" : "No lecturers in this session"}
              </option>
              {coverCandidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.busy ? `${c.label} — teaching this slot` : c.label}
                </option>
              ))}
            </select>
            <p className="muted lecturer-cover-hint">
              Single-click a class on the left, then double-click it to create a cover request for{" "}
              {coverStaffId
                ? coverCandidates.find((c) => c.id === coverStaffId)?.label ?? "the cover lecturer"
                : "the selected cover lecturer"}
              .
            </p>

            <div className="lecturer-cover-log-send">
              {hasCalendar && (
                <>
                  <label className="lecturer-cover-toolbar-label" htmlFor="cover-sem">
                    Semester
                  </label>
                  <select
                    id="cover-sem"
                    className="field-select"
                    value={coverSemester}
                    onChange={(e) => setCoverSemester(Number(e.target.value))}
                  >
                    {semesters.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <label className="lecturer-cover-toolbar-label" htmlFor="cover-week">
                    Week
                  </label>
                  <select
                    id="cover-week"
                    className="field-select"
                    value={coverWeek}
                    onChange={(e) => setCoverWeek(Number(e.target.value))}
                  >
                    {weeksForSemester.map((w) => (
                      <option key={w.week_number} value={w.week_number}>
                        {w.week_number}{w.label ? ` (${w.label})` : ""}
                      </option>
                    ))}
                  </select>
                </>
              )}
              <label className="lecturer-cover-toolbar-label" htmlFor="cover-date">
                {hasCalendar ? "Date (override)" : "Cover date"}
              </label>
              <input
                id="cover-date"
                type="date"
                className="field-input"
                value={coverDate}
                onChange={(e) => setCoverDate(e.target.value)}
              />
            </div>
          </div>
        )}

        <div className="lecturer-cover-toolbar-actions">
          <span className="tt-zoom-label">{displayZoomPercent(gridZoom)}%</span>
          <button type="button" className="btn-secondary btn-xs" onClick={() => setGridZoom(zoomOut(gridZoom))}>
            −
          </button>
          <button type="button" className="btn-secondary btn-xs" onClick={() => setGridZoom(zoomIn(gridZoom))}>
            +
          </button>
          <button type="button" className="btn-secondary btn-xs" onClick={() => setGridZoom(resetGridZoom())}>
            100%
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={requests.length === 0}
            onClick={() => void copyTimetableToClipboard()}
          >
            {copied ? "Copied ✓" : "Copy timetable for email"}
          </button>
        </div>
      </div>

      <div className="lecturer-cover-split">
        <section className="lecturer-cover-pane">
          <header className="lecturer-cover-pane-title">
            {leftGrid?.entity_label ?? "Lecturer requiring cover"}
          </header>
          {leftLoading && !leftGrid ? (
            <LoadingMark label="Loading timetable…" />
          ) : displayLeftGrid ? (
            <WeekGridView
              grid={displayLeftGrid}
              sessionId={sessionId}
              viewKind="staff"
              editable={false}
              zoom={gridZoom}
              showAlerts={showAlerts}
              colourByClass={colourByClass}
              fitToViewport
              selectedBookingId={selectedBookingId}
              onSelectedBookingChange={setSelectedBookingId}
              coverAssignMode
              onAssignCover={(b) => void assignCover(b)}
            />
          ) : (
            <p className="muted lecturer-cover-empty">Select a lecturer requiring cover.</p>
          )}
        </section>

        <section className="lecturer-cover-pane">
          <header className="lecturer-cover-pane-title">
            {rightGrid?.entity_label ?? "Cover lecturer"}
          </header>
          {rightLoading && !rightGrid ? (
            <LoadingMark label="Loading timetable…" />
          ) : rightGrid ? (
            <WeekGridView
              grid={rightGrid}
              sessionId={sessionId}
              viewKind="staff"
              editable={false}
              zoom={gridZoom}
              showAlerts={showAlerts}
              colourByClass={colourByClass}
              fitToViewport
            />
          ) : (
            <p className="muted lecturer-cover-empty">
              {selectedBooking
                ? "Select an available cover lecturer."
                : "Select a class on the left to see cover options."}
            </p>
          )}
        </section>
      </div>

      <section className="lecturer-cover-requests">
        <header className="lecturer-cover-pane-title">
          Pending cover requests ({requests.length})
        </header>
        {requests.length === 0 ? (
          <p className="muted lecturer-cover-empty">
            No pending requests. Select a class above, choose a cover lecturer, and double-click the
            class to create one. Requests stay here (editable) until you push them to the global log.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Day / Time</th>
                  <th>Group</th>
                  <th>Class</th>
                  <th>Room</th>
                  <th>Away lecturer</th>
                  <th>Cover lecturer</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => {
                  const busy = busyRequestId === r.id;
                  const canPush = globalSessionId != null && !!r.cover_date && r.cover_staff_id != null;
                  return (
                    <tr key={r.id}>
                      <td>
                        <input
                          type="date"
                          className="field-input cover-request-date"
                          value={r.cover_date ?? ""}
                          disabled={busy}
                          onChange={(e) => void changeRequestDate(r, e.target.value)}
                        />
                      </td>
                      <td>{[r.day_label, r.time_label].filter(Boolean).join(" ")}</td>
                      <td>{r.group_name}</td>
                      <td>{r.unit_name}</td>
                      <td>{r.room_code}</td>
                      <td>{r.away_staff_name}</td>
                      <td>
                        <select
                          className="field-select cover-request-cover"
                          value={r.cover_staff_id ?? ""}
                          disabled={busy}
                          onChange={(e) =>
                            void changeRequestCover(
                              r,
                              e.target.value === "" ? null : Number(e.target.value),
                            )
                          }
                        >
                          <option value="">Unassigned…</option>
                          {staff.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="cover-request-actions">
                        <button
                          type="button"
                          className="btn-primary btn-xs"
                          disabled={busy || !canPush}
                          title={
                            globalSessionId == null
                              ? "This session isn't part of a global group."
                              : !r.cover_staff_id
                                ? "Assign a cover lecturer first."
                                : !r.cover_date
                                  ? "Set a cover date first."
                                  : "Log this cover globally and remove it from here"
                          }
                          onClick={() => void pushRequestToLog(r)}
                        >
                          Push to log
                        </button>
                        <button
                          type="button"
                          className="btn-secondary btn-xs"
                          disabled={busy}
                          onClick={() => void deleteRequest(r)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
