/** Arrange cover from a phone.
 *
 * Pick the lecturer who is away, tap the class they cannot take, choose from
 * the lecturers actually free at that hour, then hand the result on: either as
 * the standard email to both of them, or as a record in the global cover log.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type CoverCandidate } from "../api";
import { MobileWeekGrid } from "./MobileWeekGrid";
import { buildCoverEmail, coverDetailLines, type CoverEmailFacts } from "./coverEmail";
import {
  minutesToLabel,
  slotToMinutes,
  type LecturerWeek,
} from "./lecturerWeek";

type Card = LecturerWeek["bookings"][number];

type Props = {
  week: LecturerWeek | null;
  loading: boolean;
  /** Workspace a session belongs to; null when it is linked to none. */
  globalSessionIdFor: (sessionId: number) => number | null;
  onError?: (message: string) => void;
};

/** The next occurrence of a weekday, today included. */
function nextDateFor(dayIndex: number, from: Date = new Date()): string {
  const todayIdx = (from.getDay() + 6) % 7; // 0 = Monday
  const delta = (dayIndex - todayIdx + 7) % 7;
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + delta);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function MobileCoverView({ week, loading, globalSessionIdFor, onError }: Props) {
  const [picked, setPicked] = useState<Card | null>(null);
  const [candidates, setCandidates] = useState<CoverCandidate[] | null>(null);
  const [coverId, setCoverId] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const [copied, setCopied] = useState(false);
  const [logged, setLogged] = useState(false);
  const [busy, setBusy] = useState(false);

  // A new class means a new set of candidates and a fresh outcome.
  useEffect(() => {
    setCandidates(null);
    setCoverId(null);
    setCopied(false);
    setLogged(false);
    if (!picked) return;
    setDate(nextDateFor(picked.day));
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.coverCandidates(picked.sessionId, picked.id);
        if (!cancelled) setCandidates(data.candidates);
      } catch (err) {
        if (!cancelled) {
          setCandidates([]);
          onError?.(err instanceof Error ? err.message : "Could not load cover lecturers");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [picked, onError]);

  const facts = useCallback((): CoverEmailFacts | null => {
    if (!picked || !week) return null;
    const cover = candidates?.find((c) => c.id === coverId);
    if (!cover) return null;
    const start = minutesToLabel(
      slotToMinutes(picked.start_slot, week.firstSlotTime, week.slotMinutes),
    );
    const end = minutesToLabel(
      slotToMinutes(picked.end_slot, week.firstSlotTime, week.slotMinutes),
    );
    return {
      date,
      dayLabel: week.days[picked.day] ?? `Day ${picked.day + 1}`,
      timeLabel: `${start} – ${end}`,
      groupName: picked.course_code ?? "",
      unitName: picked.unit_name ?? picked.course_code ?? "Class",
      roomCode: picked.room_code ?? "",
      awayStaffName: week.name,
      coverStaffName: cover.label,
    };
  }, [picked, week, candidates, coverId, date]);

  async function copyEmail() {
    const f = facts();
    if (!f) return;
    try {
      await navigator.clipboard.writeText(buildCoverEmail(f));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Could not copy the email");
    }
  }

  async function sendToLog() {
    const f = facts();
    const workspaceId = picked ? globalSessionIdFor(picked.sessionId) : null;
    if (!f || !picked || workspaceId == null) return;
    setBusy(true);
    try {
      await api.createCoverLogEntry(workspaceId, {
        cover_date: f.date,
        day_label: f.dayLabel,
        time_label: f.timeLabel,
        group_name: f.groupName,
        unit_name: f.unitName,
        room_code: f.roomCode,
        away_staff_name: f.awayStaffName,
        cover_staff_name: f.coverStaffName,
        source_session_name: picked.sessionName,
      });
      setLogged(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not send to the cover log";
      onError?.(
        /403|forbidden|permission/i.test(msg)
          ? "You have read-only access, so this cannot be written to the cover log. The email above still works."
          : msg,
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="mv-empty">Loading…</p>;
  if (!week) return <p className="mv-empty">Choose the lecturer who needs cover.</p>;
  if (!week.bookings.length) {
    return <p className="mv-empty">{week.name} has no classes to cover.</p>;
  }

  const f = facts();

  return (
    <div className="mv-cover">
      <div className="mv-cover-grid">
        <MobileWeekGrid
          week={week}
          onSelectBooking={setPicked}
          selectedBookingId={picked?.id ?? null}
        />
      </div>

      {!picked ? (
        <p className="mv-cover-hint">Tap the class that needs covering.</p>
      ) : (
        <aside className="mv-cover-panel" aria-label="Arrange cover">
          <header className="mv-cover-head">
            <strong>{picked.unit_name ?? picked.course_code ?? "Class"}</strong>
            <button
              type="button"
              className="mv-cover-clear"
              onClick={() => setPicked(null)}
              aria-label="Choose a different class"
            >
              ✕
            </button>
          </header>

          <label className="mv-cover-field">
            <span>Date</span>
            <input
              type="date"
              className="mv-input"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>

          <label className="mv-cover-field">
            <span>Cover lecturer</span>
            <select
              className="mv-select"
              value={coverId ?? ""}
              onChange={(e) => setCoverId(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">
                {candidates == null
                  ? "Loading…"
                  : candidates.length
                    ? "Select…"
                    : "No lecturers available"}
              </option>
              {(candidates ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.under_hours ? `● ${c.label}` : c.label}
                  {c.busy ? " — teaching this slot" : ""}
                </option>
              ))}
            </select>
          </label>

          {f && (
            <ul className="mv-cover-detail">
              {coverDetailLines(f).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}

          <div className="mv-cover-actions">
            <button
              type="button"
              className="mv-cover-btn mv-cover-btn--primary"
              disabled={!f}
              onClick={() => void copyEmail()}
            >
              {copied ? "Copied ✓" : "Copy email"}
            </button>
            <button
              type="button"
              className="mv-cover-btn"
              disabled={
                !f || busy || logged || !picked || globalSessionIdFor(picked.sessionId) == null
              }
              onClick={() => void sendToLog()}
              title={
                picked && globalSessionIdFor(picked.sessionId) == null
                  ? "This timetable is not linked to a workspace, so there is no cover log to write to"
                  : undefined
              }
            >
              {logged ? "Sent ✓" : busy ? "Sending…" : "Send to cover log"}
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
