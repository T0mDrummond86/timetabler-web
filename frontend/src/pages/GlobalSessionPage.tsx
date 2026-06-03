import { Link, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
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
import { LinkedSessionImportPanel } from "../components/LinkedSessionImportPanel";

type Tab = "staff" | "rooms" | "units" | "qualifications" | "custodians" | "members";

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
  }, [tab, globalSessionId, loading]);

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
        <p className="muted">Loading…</p>
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
            if (tab !== "members") return;
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
        <AggregatedTable
          headers={["Session", "Name", "FTE", "Non-teaching day"]}
          empty="No staff in linked sessions."
          rows={staff.map((r) => [
            r.session_name,
            r.name,
            r.fte ?? "—",
            r.non_teaching_day != null ? ["Mon", "Tue", "Wed", "Thu", "Fri"][r.non_teaching_day] ?? r.non_teaching_day : "—",
          ])}
        />
      )}

      {tab === "rooms" && (
        <AggregatedTable
          headers={["Session", "Code", "Name", "Type", "Capacity"]}
          empty="No rooms in linked sessions."
          rows={rooms.map((r) => [
            r.session_name,
            r.code,
            r.name ?? "—",
            r.room_type ?? "—",
            r.capacity ?? "—",
          ])}
        />
      )}

      {tab === "units" && (
        <AggregatedTable
          headers={["Session", "Class", "Length (h)", "Double session"]}
          empty="No classes in linked sessions."
          rows={units.map((r) => [
            r.session_name,
            r.name,
            r.length_slots ? r.length_slots / 2 : "—",
            r.double_session ? "Yes" : "—",
          ])}
        />
      )}

      {tab === "qualifications" && (
        <AggregatedTable
          headers={["Session", "Qualification", "Groups", "Period"]}
          empty="No qualifications in linked sessions."
          rows={quals.map((r) => [
            r.session_name,
            r.name,
            r.num_groups ?? "—",
            r.schedule_period ?? "—",
          ])}
        />
      )}

      {tab === "custodians" && (
        <section className="card">
          <p className="muted">{custodians?.summary ?? "Loading…"}</p>
          <AggregatedTable
            headers={["Session", "Class", "Lecturers", "Custodian"]}
            empty="No class custodian data."
            rows={(custodians?.rows ?? []).map((r) => [
              r.session_name,
              r.unit_name,
              r.lecturers,
              r.custodian_name ?? "—",
            ])}
          />
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
