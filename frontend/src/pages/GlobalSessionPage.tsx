import { Link, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  GlobalSession,
  GlobalAggregatedQualRow,
  GlobalAggregatedRoomRow,
  GlobalAggregatedStaffRow,
  GlobalAggregatedUnitRow,
  TimetableSession,
} from "../api";
import type { GlobalClassCustodians } from "../types";
import { AppShell } from "../components/AppShell";
import { ClassCustodiansTable } from "../components/ClassCustodiansTable";
import {
  formatGlobalVariance,
  GlobalFilteredAggregateTable,
  qualificationListFilter,
  sessionFilter,
  uniqFieldFilter,
  varianceSignFilter,
} from "../components/GlobalFilteredAggregateTable";
import { LinkedSessionImportPanel } from "../components/LinkedSessionImportPanel";
import { LoadingMark } from "../components/LoadingMark";
import { useSessionSync } from "../lib/sessionSync";

type Tab = "staff" | "rooms" | "units" | "qualifications" | "custodians" | "members";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"];

function formatSessions(sessionNames: string[]): string {
  return sessionNames.join(", ");
}

function formatNonTeachingDay(value: number | string | null | undefined): string | number {
  if (value === "Varies") return "Varies";
  if (value == null) return "—";
  if (typeof value === "number" && value >= 0 && value <= 4) return DAY_NAMES[value] ?? value;
  return String(value);
}

function formatLengthHours(slots: number | string | null | undefined): string | number {
  if (slots === "Varies") return "Varies";
  if (slots == null) return "—";
  if (typeof slots === "number") return slots / 2;
  return String(slots);
}

function formatDoubleSession(value: number | string | undefined): string {
  if (value === "Varies") return "Varies";
  return value ? "Yes" : "No";
}

function formatVaries(value: string | number | null | undefined): string | number {
  if (value === "Varies") return "Varies";
  if (value == null) return "—";
  return value;
}

const TABS: { id: Tab; label: string }[] = [
  { id: "members", label: "Linked sessions" },
  { id: "staff", label: "Staff" },
  { id: "rooms", label: "Rooms" },
  { id: "units", label: "Classes" },
  { id: "qualifications", label: "Qualifications" },
  { id: "custodians", label: "Class custodians" },
];

export function GlobalSessionPage() {
  const { globalSessionId: idParam } = useParams();
  const globalSessionId = Number(idParam);
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("members");
  const [global, setGlobal] = useState<GlobalSession | null>(null);
  const [allSessions, setAllSessions] = useState<TimetableSession[]>([]);
  const [selectedMemberIds, setSelectedMemberIds] = useState<number[]>([]);
  const [staff, setStaff] = useState<GlobalAggregatedStaffRow[]>([]);
  const [rooms, setRooms] = useState<GlobalAggregatedRoomRow[]>([]);
  const [units, setUnits] = useState<GlobalAggregatedUnitRow[]>([]);
  const [quals, setQuals] = useState<GlobalAggregatedQualRow[]>([]);
  const [custodians, setCustodians] = useState<GlobalClassCustodians | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tabSyncToken, setTabSyncToken] = useState(0);

  const memberSessionIds = useMemo(
    () => global?.member_sessions.map((m) => m.id) ?? [],
    [global?.member_sessions.map((m) => m.id).join(",")],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const orgs = await api.orgs();
      if (!orgs.length) throw new Error("No organization");
      const [g, sessions] = await Promise.all([
        api.globalSession(globalSessionId),
        api.sessions(orgs[0].id),
      ]);
      setGlobal(g);
      setAllSessions(sessions);
      setSelectedMemberIds(g.member_sessions.map((m) => m.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [globalSessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useSessionSync(
    memberSessionIds[0] ?? 0,
    () => setTabSyncToken((t) => t + 1),
    memberSessionIds.length ? memberSessionIds : undefined,
  );

  useEffect(() => {
    if (tab === "members" || loading) return;
    let cancelled = false;
    (async () => {
      try {
        if (tab === "staff") {
          const data = await api.globalSessionStaff(globalSessionId);
          if (!cancelled) setStaff(data.rows);
        } else if (tab === "rooms") {
          const data = await api.globalSessionRooms(globalSessionId);
          if (!cancelled) setRooms(data.rows);
        } else if (tab === "units") {
          const data = await api.globalSessionUnits(globalSessionId);
          if (!cancelled) setUnits(data.rows);
        } else if (tab === "qualifications") {
          const data = await api.globalSessionQualifications(globalSessionId);
          if (!cancelled) setQuals(data.rows);
        } else if (tab === "custodians") {
          const data = await api.globalSessionClassCustodians(globalSessionId);
          if (!cancelled) setCustodians(data);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load tab");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, globalSessionId, loading, tabSyncToken]);

  async function saveMembers() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.setGlobalSessionMembers(globalSessionId, selectedMemberIds);
      setGlobal(updated);
      setSelectedMemberIds(updated.member_sessions.map((m) => m.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleMember(sessionId: number) {
    setSelectedMemberIds((prev) =>
      prev.includes(sessionId) ? prev.filter((id) => id !== sessionId) : [...prev, sessionId],
    );
  }

  if (loading && !global) {
    return (
      <AppShell title="Global session">
        <LoadingMark label="Loading…" />
      </AppShell>
    );
  }

  return (
    <AppShell
      wide
      breadcrumb={
        <>
          <Link to="/dashboard">Dashboard</Link>
          <span aria-hidden> / </span>
          Global session
        </>
      }
      title={global?.name ?? "Global session"}
      subtitle={
        <span className="muted">
          Combined staff, rooms, and classes from linked timetable sessions. No timetable editing
          here — open a linked session to schedule. Staff busy in one session appear greyed out in
          others.
        </span>
      }
    >
      {error && <div className="error-banner">{error}</div>}

      <div className="session-tabs global-session-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? "session-tab active" : "session-tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "members" && global && global.member_sessions.length >= 2 && (
        <LinkedSessionImportPanel
          targetSessionId={global.member_sessions[0]?.id ?? 0}
          targetOptions={global.member_sessions}
          onImported={() => {
            void load();
            void api.globalSessionStaff(globalSessionId).then((d) => setStaff(d.rows)).catch(() => {});
            void api
              .globalSessionQualifications(globalSessionId)
              .then((d) => setQuals(d.rows))
              .catch(() => {});
            void api.globalSessionUnits(globalSessionId).then((d) => setUnits(d.rows)).catch(() => {});
          }}
        />
      )}

      {tab === "members" && (
        <section className="card global-members-card">
          <h2>Linked timetable sessions</h2>
          <p className="muted">
            Select which individual timetable sessions belong to this global group.
          </p>
          <ul className="global-member-list">
            {allSessions.map((s) => {
              const inOther =
                s.global_session_id != null && s.global_session_id !== globalSessionId;
              return (
                <li key={s.id}>
                  <label className={inOther ? "global-member-disabled" : "checkbox"}>
                    <input
                      type="checkbox"
                      checked={selectedMemberIds.includes(s.id)}
                      disabled={inOther}
                      onChange={() => toggleMember(s.id)}
                    />
                    <span>
                      {s.name}
                      {s.global_session_id === globalSessionId && (
                        <span className="muted"> (linked)</span>
                      )}
                      {inOther && (
                        <span className="muted"> — in {s.global_session_name}</span>
                      )}
                    </span>
                  </label>
                  <Link to={`/timetable/${s.id}`} className="btn-secondary btn-xs">
                    Open timetable
                  </Link>
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            className="btn-primary"
            disabled={saving}
            onClick={() => void saveMembers()}
          >
            {saving ? "Saving…" : "Save linked sessions"}
          </button>
        </section>
      )}

      {tab === "staff" && (
        <GlobalFilteredAggregateTable
          rows={staff}
          empty="No staff in linked sessions."
          filters={[
            sessionFilter<GlobalAggregatedStaffRow>(),
            uniqFieldFilter<GlobalAggregatedStaffRow>("fte", "FTE", (r) => r.fte),
            uniqFieldFilter<GlobalAggregatedStaffRow>(
              "non_teaching_day",
              "Non-teaching day",
              (r) => r.non_teaching_day,
              (v) => {
                if (v === "—" || v === "Varies") return v;
                return String(formatNonTeachingDay(Number(v)));
              },
            ),
            varianceSignFilter<GlobalAggregatedStaffRow>(),
          ]}
          columns={[
            { header: "Name", cell: (r) => r.name },
            { header: "Used in sessions", cell: (r) => formatSessions(r.session_names) },
            { header: "FTE", cell: (r) => formatVaries(r.fte) },
            {
              header: "Non-teaching day",
              cell: (r) => formatNonTeachingDay(r.non_teaching_day),
            },
            {
              header: "Variance",
              cell: (r) => formatGlobalVariance(r.variance),
              cellClassName: (r) => {
                const v = r.variance;
                if (typeof v !== "number") return undefined;
                if (v < -0.001) return "variance-cell variance-full-fte-shortfall";
                if (v > 0.001) return "variance-cell variance-full-fte-overtime";
                return "variance-cell";
              },
            },
          ]}
        />
      )}

      {tab === "rooms" && (
        <AggregatedTable
          headers={["Code", "Used in sessions", "Name", "Type", "Capacity"]}
          empty="No rooms in linked sessions."
          rows={rooms.map((r) => [
            r.code,
            formatSessions(r.session_names),
            formatVaries(r.name),
            formatVaries(r.room_type),
            formatVaries(r.capacity),
          ])}
        />
      )}

      {tab === "units" && (
        <GlobalFilteredAggregateTable
          rows={units}
          empty="No classes in linked sessions."
          filters={[
            sessionFilter<GlobalAggregatedUnitRow>(),
            qualificationListFilter<GlobalAggregatedUnitRow>(
              (r: GlobalAggregatedUnitRow) => r.qualifications ?? "—",
            ),
          ]}
          columns={[
            { header: "Class", cell: (r) => r.name },
            { header: "Used in sessions", cell: (r) => formatSessions(r.session_names) },
            { header: "Linked qualifications", cell: (r) => r.qualifications ?? "—" },
            { header: "Length (h)", cell: (r) => formatLengthHours(r.length_slots) },
            { header: "Double session", cell: (r) => formatDoubleSession(r.double_session) },
          ]}
        />
      )}

      {tab === "qualifications" && (
        <GlobalFilteredAggregateTable
          rows={quals}
          empty="No qualifications in linked sessions."
          filters={[
            sessionFilter<GlobalAggregatedQualRow>(),
            uniqFieldFilter<GlobalAggregatedQualRow>(
              "period",
              "Period",
              (r: GlobalAggregatedQualRow) => r.schedule_period,
            ),
          ]}
          columns={[
            { header: "Qualification", cell: (r) => r.name },
            { header: "Used in sessions", cell: (r) => formatSessions(r.session_names) },
            { header: "Groups", cell: (r) => formatVaries(r.num_groups) },
            { header: "Period", cell: (r) => formatVaries(r.schedule_period) },
          ]}
        />
      )}

      {tab === "custodians" && (
        <section className="card class-custodians-panel">
          {loading && !custodians ? (
            <LoadingMark label="Loading…" />
          ) : (
            <ClassCustodiansTable
              amalgamatedSessions
              summary={custodians?.summary}
              emptyMessage="No class custodian rows match the current filters."
              rows={(custodians?.rows ?? []).map((r) => ({
                unit_id: r.unit_id,
                unit_name: r.unit_name,
                qualifications: r.qualifications ?? "—",
                lecturers: r.lecturers,
                custodian: r.custodian,
                session_names: r.session_names,
              }))}
            />
          )}
        </section>
      )}

      <p className="muted" style={{ marginTop: "1.5rem" }}>
        <button type="button" className="btn-secondary" onClick={() => navigate("/dashboard")}>
          Back to dashboard
        </button>
      </p>
    </AppShell>
  );
}

function AggregatedTable({
  headers,
  rows,
  empty,
}: {
  headers: string[];
  rows: (string | number)[][];
  empty: string;
}) {
  return (
    <section className="card global-aggregate-table-wrap">
      <div className="global-aggregate-table-scroll">
        <table className="global-aggregate-table">
          <thead>
            <tr>
              {headers.map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={headers.length} className="muted empty-cell">
                  {empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
