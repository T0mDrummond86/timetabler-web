import { FormEvent, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  getToken,
  GlobalSessionSummary,
  Organization,
  setToken,
  TimetableSession,
  User,
} from "../api";
import { AppShell } from "../components/AppShell";
import { DropdownGroup } from "../components/DropdownGroup";
import { LoadingMark } from "../components/LoadingMark";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";
import { useDropdown } from "../hooks/useDropdown";
import { formatRelativeTime } from "../lib/formatRelativeTime";
import { readRecentSessionIds, recentRank, recordSessionOpen } from "../lib/recentSessions";

type SortMode = "recent" | "updated" | "name";

function StatusBanner({
  kind,
  message,
  onDismiss,
  action,
}: {
  kind: "error" | "success";
  message: string;
  onDismiss: () => void;
  action?: ReactNode;
}) {
  return (
    <div className={`${kind}-banner`} role={kind === "error" ? "alert" : "status"}>
      <div className="status-banner-body">
        <span>{message}</span>
        {action}
      </div>
      <button
        type="button"
        className="success-banner-dismiss"
        onClick={onDismiss}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

function RowMenu({
  label,
  busy,
  items,
}: {
  label: string;
  busy?: boolean;
  items: { id: string; label: string; danger?: boolean; onClick: () => void }[];
}) {
  const menu = useDropdown();

  return (
    <span className="tt-dropdown-wrap dashboard-row-menu" ref={menu.wrapRef}>
      <button
        type="button"
        className="btn-ghost btn-xs dashboard-row-menu-btn"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          menu.toggle();
        }}
        disabled={busy}
        aria-expanded={menu.open}
        aria-haspopup="menu"
        aria-label={`${label} actions`}
      >
        {busy ? "…" : "⋯"}
      </button>
      {menu.open && (
        <div className="tt-dropdown-menu dashboard-row-dropdown" role="menu">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className={`ctx-item${item.danger ? " ctx-item-danger" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                menu.close();
                item.onClick();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

function sessionMeta(session: TimetableSession): string {
  const courses = session.course_count ?? 0;
  const bookings = session.booking_count ?? 0;
  const parts = [
    `${courses} course${courses === 1 ? "" : "s"}`,
    `${bookings} booking${bookings === 1 ? "" : "s"}`,
    `Updated ${formatRelativeTime(session.updated_at)}`,
  ];
  return parts.join(" · ");
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [sessions, setSessions] = useState<TimetableSession[]>([]);
  const [globalSessions, setGlobalSessions] = useState<GlobalSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [newSessionName, setNewSessionName] = useState("");
  const [newGlobalName, setNewGlobalName] = useState("");
  const [creatingSession, setCreatingSession] = useState(false);
  const [creatingGlobal, setCreatingGlobal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [successAction, setSuccessAction] = useState<ReactNode>(null);
  const [busySessionId, setBusySessionId] = useState<number | null>(null);
  const [busyGlobalId, setBusyGlobalId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortMode>("recent");
  const [recentIds, setRecentIds] = useState<number[]>(() => readRecentSessionIds());
  const { confirm, prompt, dialogs } = useConfirmPrompt();

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    (async () => {
      setLoading(true);
      try {
        const [u, o] = await Promise.all([api.me(), api.orgs()]);
        setUser(u);
        setOrgs(o);
        if (o.length) {
          const [s, g] = await Promise.all([api.sessions(o[0].id), api.globalSessions(o[0].id)]);
          setSessions(s);
          setGlobalSessions(g);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
        setToken(null);
        navigate("/login");
      } finally {
        setLoading(false);
      }
    })();
  }, [navigate]);

  const org = orgs[0];

  const filteredSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = sessions;
    if (q) {
      rows = rows.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          (s.global_session_name ?? "").toLowerCase().includes(q),
      );
    }
    const sorted = [...rows];
    if (sort === "name") {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === "updated") {
      sorted.sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
    } else {
      sorted.sort((a, b) => {
        const ra = recentRank(a.id, recentIds);
        const rb = recentRank(b.id, recentIds);
        if (ra !== rb) return ra - rb;
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
    }
    return sorted;
  }, [sessions, search, sort, recentIds]);

  const filteredGlobals = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return globalSessions;
    return globalSessions.filter((g) => g.name.toLowerCase().includes(q));
  }, [globalSessions, search]);

  function clearBanners() {
    setError(null);
    setSuccess(null);
    setSuccessAction(null);
  }

  async function createSession(e?: FormEvent) {
    e?.preventDefault();
    if (!orgs.length || !newSessionName.trim()) return;
    setCreatingSession(true);
    clearBanners();
    try {
      const row = await api.createSession(orgs[0].id, newSessionName.trim());
      setSessions((prev) => [...prev, row].sort((a, b) => a.name.localeCompare(b.name)));
      setNewSessionName("");
      setSuccess(`Created “${row.name}”.`);
      setSuccessAction(
        <Link to={`/timetable/${row.id}`} className="status-banner-link">
          Open session
        </Link>,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreatingSession(false);
    }
  }

  async function createGlobalSession(e?: FormEvent) {
    e?.preventDefault();
    if (!orgs.length || !newGlobalName.trim()) return;
    setCreatingGlobal(true);
    clearBanners();
    try {
      const row = await api.createGlobalSession(orgs[0].id, newGlobalName.trim());
      const summary: GlobalSessionSummary = {
        id: row.id,
        organization_id: row.organization_id,
        name: row.name,
        member_count: row.member_sessions.length,
        created_at: row.created_at,
        updated_at: row.updated_at,
      };
      setGlobalSessions((prev) =>
        [...prev, summary].sort((a, b) => a.name.localeCompare(b.name)),
      );
      setNewGlobalName("");
      setSuccess(`Created global session “${row.name}”.`);
      setSuccessAction(
        <Link to={`/global/${row.id}`} className="status-banner-link">
          Open global session
        </Link>,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreatingGlobal(false);
    }
  }

  async function renameSession(session: TimetableSession) {
    const name = await prompt({
      title: "Rename session",
      defaultValue: session.name,
      placeholder: "Session name",
      confirmLabel: "Rename",
    });
    if (!name?.trim() || name.trim() === session.name) return;
    setBusySessionId(session.id);
    clearBanners();
    try {
      const row = await api.patchSession(session.id, name.trim());
      setSessions((prev) =>
        prev
          .map((s) => (s.id === row.id ? row : s))
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
      setSuccess(`Renamed to “${row.name}”.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setBusySessionId(null);
    }
  }

  async function saveSessionAs(session: TimetableSession) {
    const suggested = `${session.name} copy`;
    const name = await prompt({
      title: "Save session as",
      message: "Create a copy of this timetable under a new name.",
      defaultValue: suggested,
      placeholder: "Session name",
      confirmLabel: "Save copy",
    });
    if (!name?.trim()) return;
    setBusySessionId(session.id);
    clearBanners();
    try {
      const row = await api.duplicateSession(session.id, name.trim());
      setSessions((prev) => [...prev, row].sort((a, b) => a.name.localeCompare(b.name)));
      recordSessionOpen(row.id);
      setRecentIds(readRecentSessionIds());
      navigate(`/timetable/${row.id}`, { state: { flash: `Copied to “${row.name}”.` } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save as failed");
      setBusySessionId(null);
    }
  }

  async function deleteSession(session: TimetableSession) {
    const linked = session.global_session_name
      ? ` It is linked in global session “${session.global_session_name}”.`
      : "";
    if (
      !(await confirm({
        title: "Delete session",
        message: `Delete “${session.name}”? All timetable data in this session will be permanently removed.${linked}`,
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
    setBusySessionId(session.id);
    clearBanners();
    try {
      await api.deleteSession(session.id);
      setSessions((prev) => prev.filter((s) => s.id !== session.id));
      setGlobalSessions((prev) =>
        prev.map((g) =>
          session.global_session_id === g.id
            ? { ...g, member_count: Math.max(0, g.member_count - 1) }
            : g,
        ),
      );
      setSuccess(`Deleted “${session.name}”.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusySessionId(null);
    }
  }

  async function renameGlobalSession(global: GlobalSessionSummary) {
    const name = await prompt({
      title: "Rename global session",
      defaultValue: global.name,
      placeholder: "Global session name",
      confirmLabel: "Rename",
    });
    if (!name?.trim() || name.trim() === global.name) return;
    setBusyGlobalId(global.id);
    clearBanners();
    try {
      const row = await api.updateGlobalSession(global.id, name.trim());
      setGlobalSessions((prev) =>
        prev
          .map((g) =>
            g.id === row.id
              ? {
                  ...g,
                  name: row.name,
                  updated_at: row.updated_at,
                }
              : g,
          )
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
      setSessions((prev) =>
        prev.map((s) =>
          s.global_session_id === row.id ? { ...s, global_session_name: row.name } : s,
        ),
      );
      setSuccess(`Renamed global session to “${row.name}”.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setBusyGlobalId(null);
    }
  }

  async function deleteGlobalSession(global: GlobalSessionSummary) {
    if (
      !(await confirm({
        title: "Delete global session",
        message: `Delete “${global.name}”? Linked timetable sessions are not deleted — only the global link group.`,
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
    setBusyGlobalId(global.id);
    clearBanners();
    try {
      await api.deleteGlobalSession(global.id);
      setGlobalSessions((prev) => prev.filter((g) => g.id !== global.id));
      setSessions((prev) =>
        prev.map((s) =>
          s.global_session_id === global.id
            ? { ...s, global_session_id: null, global_session_name: null }
            : s,
        ),
      );
      setSuccess(`Deleted global session “${global.name}”.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyGlobalId(null);
    }
  }

  function openSession(session: TimetableSession) {
    recordSessionOpen(session.id);
    setRecentIds(readRecentSessionIds());
  }

  return (
    <AppShell
      title="Dashboard"
      subtitle={
        user
          ? `${user.name || user.email}${org ? ` · ${org.name}` : ""}`
          : undefined
      }
      actions={
        <button type="button" className="btn-secondary" onClick={() => {
          setToken(null);
          navigate("/login");
        }}>
          Sign out
        </button>
      }
    >
      <DropdownGroup>
        {error && (
          <StatusBanner kind="error" message={error} onDismiss={() => setError(null)} />
        )}
        {success && (
          <StatusBanner
            kind="success"
            message={success}
            action={successAction}
            onDismiss={() => {
              setSuccess(null);
              setSuccessAction(null);
            }}
          />
        )}

        <section className="card dashboard-card">
          <div className="dashboard-card-header">
            <h2>Timetable sessions</h2>
            <form className="dashboard-create-form" onSubmit={(e) => void createSession(e)}>
              <input
                className="field-input"
                placeholder="New session name"
                value={newSessionName}
                onChange={(e) => setNewSessionName(e.target.value)}
                aria-label="New session name"
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={!newSessionName.trim() || creatingSession}
              >
                {creatingSession ? "Creating…" : "New session"}
              </button>
            </form>
          </div>

          {sessions.length > 0 && (
            <div className="dashboard-toolbar">
              <input
                type="search"
                className="field-input dashboard-search"
                placeholder="Search sessions…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search sessions"
              />
              <label className="dashboard-sort">
                <span className="muted">Sort</span>
                <select
                  className="field-select"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortMode)}
                >
                  <option value="recent">Recently opened</option>
                  <option value="updated">Recently updated</option>
                  <option value="name">Name A–Z</option>
                </select>
              </label>
            </div>
          )}

          {loading ? (
            <LoadingMark label="Loading sessions…" />
          ) : !sessions.length ? (
            <p className="muted panel-empty">No sessions yet.</p>
          ) : filteredSessions.length === 0 ? (
            <p className="muted panel-empty">No sessions match your search.</p>
          ) : (
            <ul className="session-list dashboard-session-list">
              {filteredSessions.map((s) => (
                <li key={s.id} className="dashboard-session-row">
                  <Link
                    to={`/timetable/${s.id}`}
                    className="dashboard-session-main"
                    onClick={() => openSession(s)}
                  >
                    <div className="dashboard-session-title">
                      <strong>{s.name}</strong>
                      {s.global_session_name && (
                        <span className="session-badge" title={s.global_session_name}>
                          Linked · {s.global_session_name}
                        </span>
                      )}
                    </div>
                    <span className="muted dashboard-session-meta">{sessionMeta(s)}</span>
                  </Link>
                  <RowMenu
                    label={s.name}
                    busy={busySessionId === s.id}
                    items={[
                      { id: "rename", label: "Rename…", onClick: () => void renameSession(s) },
                      { id: "save-as", label: "Save as…", onClick: () => void saveSessionAs(s) },
                      {
                        id: "delete",
                        label: "Delete",
                        danger: true,
                        onClick: () => void deleteSession(s),
                      },
                    ]}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card dashboard-card">
          <div className="dashboard-card-header">
            <h2>Global sessions</h2>
            <form className="dashboard-create-form" onSubmit={(e) => void createGlobalSession(e)}>
              <input
                className="field-input"
                placeholder="New global session name"
                value={newGlobalName}
                onChange={(e) => setNewGlobalName(e.target.value)}
                aria-label="New global session name"
              />
              <button
                type="submit"
                className="btn-secondary"
                disabled={!newGlobalName.trim() || creatingGlobal}
              >
                {creatingGlobal ? "Creating…" : "New global"}
              </button>
            </form>
          </div>

          {loading ? (
            <LoadingMark label="Loading…" />
          ) : !globalSessions.length ? (
            <p className="muted panel-empty">No global sessions yet.</p>
          ) : filteredGlobals.length === 0 ? (
            <p className="muted panel-empty">No global sessions match your search.</p>
          ) : (
            <ul className="session-list dashboard-session-list">
              {filteredGlobals.map((g) => (
                <li key={g.id} className="dashboard-session-row">
                  <Link to={`/global/${g.id}`} className="dashboard-session-main">
                    <div className="dashboard-session-title">
                      <strong>{g.name}</strong>
                      <span className="session-badge session-badge--global">
                        {g.member_count} linked
                      </span>
                    </div>
                    <span className="muted dashboard-session-meta">
                      Updated {formatRelativeTime(g.updated_at)}
                    </span>
                  </Link>
                  <RowMenu
                    label={g.name}
                    busy={busyGlobalId === g.id}
                    items={[
                      {
                        id: "rename",
                        label: "Rename…",
                        onClick: () => void renameGlobalSession(g),
                      },
                      {
                        id: "delete",
                        label: "Delete",
                        danger: true,
                        onClick: () => void deleteGlobalSession(g),
                      },
                    ]}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </DropdownGroup>
      {dialogs}
    </AppShell>
  );
}
