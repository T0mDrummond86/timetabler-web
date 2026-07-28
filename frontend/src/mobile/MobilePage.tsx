/** Read-only lecturer timetable viewer, built for a phone in landscape.
 *
 * Deliberately narrow: sign in, pick a workspace, pick a lecturer, see their
 * week. It contains no mutating action of any kind. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, getToken, setToken, type GlobalSessionSummary } from "../api";
import {
  lecturersFromStaffRows,
  loadLecturerWeek,
  minutesToLabel,
  slotToMinutes,
  type LecturerRef,
  type LecturerWeek,
} from "./lecturerWeek";
import { MobileWeekGrid } from "./MobileWeekGrid";
import "./mobile.css";

const LAST_VIEW_KEY = "tafetabler-mobile-last";

type Remembered = { workspaceId: number; lecturer: string };

function readRemembered(): Remembered | null {
  try {
    const raw = localStorage.getItem(LAST_VIEW_KEY);
    return raw ? (JSON.parse(raw) as Remembered) : null;
  } catch {
    return null;
  }
}

export default function MobilePage() {
  const [authed, setAuthed] = useState(() => !!getToken());
  const [workspaces, setWorkspaces] = useState<GlobalSessionSummary[]>([]);
  const [workspaceId, setWorkspaceId] = useState<number | null>(null);
  const [lecturers, setLecturers] = useState<LecturerRef[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [week, setWeek] = useState<LecturerWeek | null>(null);
  const [filter, setFilter] = useState("");
  const [panelOpen, setPanelOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [portrait, setPortrait] = useState(
    () => typeof window !== "undefined" && window.innerHeight > window.innerWidth,
  );
  const restored = useRef(false);

  useEffect(() => {
    const onResize = () => setPortrait(window.innerHeight > window.innerWidth);
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, []);

  // Workspaces the signed-in user can see.
  useEffect(() => {
    if (!authed) return;
    let cancelled = false;
    void (async () => {
      setError(null);
      try {
        const orgs = await api.orgs();
        if (!orgs.length) return;
        const rows = await api.globalSessions(orgs[0].id);
        if (cancelled) return;
        setWorkspaces(rows);
        const remembered = readRemembered();
        const initial =
          rows.find((r) => r.id === remembered?.workspaceId)?.id ?? rows[0]?.id ?? null;
        setWorkspaceId(initial);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load workspaces");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authed]);

  // Lecturers in the chosen workspace.
  useEffect(() => {
    if (workspaceId == null) return;
    let cancelled = false;
    void (async () => {
      setError(null);
      try {
        const data = await api.globalSessionStaff(workspaceId);
        if (cancelled) return;
        const refs = lecturersFromStaffRows(data.rows);
        setLecturers(refs);
        // Reopen on the last lecturer, with the picker out of the way.
        const remembered = readRemembered();
        if (
          !restored.current &&
          remembered?.workspaceId === workspaceId &&
          refs.some((r) => r.name === remembered.lecturer)
        ) {
          restored.current = true;
          setSelected(remembered.lecturer);
          setPanelOpen(false);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load lecturers");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const loadWeek = useCallback(
    async (name: string) => {
      const ref = lecturers.find((l) => l.name === name);
      if (!ref) return;
      setLoading(true);
      setError(null);
      try {
        setWeek(await loadLecturerWeek(ref));
        if (workspaceId != null) {
          localStorage.setItem(
            LAST_VIEW_KEY,
            JSON.stringify({ workspaceId, lecturer: name } satisfies Remembered),
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load that timetable");
      } finally {
        setLoading(false);
      }
    },
    [lecturers, workspaceId],
  );

  useEffect(() => {
    if (selected) void loadWeek(selected);
  }, [selected, loadWeek]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? lecturers.filter((l) => l.name.toLowerCase().includes(q)) : lecturers;
  }, [lecturers, filter]);

  if (!authed) return <MobileLogin onSignedIn={() => setAuthed(true)} />;

  return (
    <div className="mv-root">
      {portrait && (
        <div className="mv-rotate" role="status">
          <span className="mv-rotate-icon" aria-hidden>
            ⟳
          </span>
          <strong>Rotate your phone</strong>
          <span>A full teaching week needs landscape. Your timetable is loaded underneath.</span>
        </div>
      )}

      <header className="mv-bar">
        <button
          type="button"
          className="mv-panel-toggle"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen((v) => !v)}
          title={panelOpen ? "Hide the picker" : "Choose a lecturer"}
        >
          {panelOpen ? "‹" : "›"}
        </button>
        <span className="mv-title">{week?.name ?? "TAFEtabler"}</span>
        {week?.weekLabel && <span className="mv-sub">{week.weekLabel}</span>}
        <span className="mv-spacer" />
        {week && <StaleIndicator week={week} onRefresh={() => selected && void loadWeek(selected)} />}
      </header>

      {error && <div className="mv-error">{error}</div>}

      <div className="mv-body">
        <aside className={`mv-panel${panelOpen ? "" : " mv-panel--closed"}`}>
          {workspaces.length > 1 && (
            <select
              className="mv-select"
              value={workspaceId ?? ""}
              onChange={(e) => {
                setWorkspaceId(Number(e.target.value));
                setSelected(null);
                setWeek(null);
              }}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          )}
          <input
            className="mv-search"
            type="search"
            placeholder="Find a lecturer…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <ul className="mv-list">
            {filtered.map((l) => (
              <li key={l.name}>
                <button
                  type="button"
                  className={`mv-list-item${selected === l.name ? " mv-list-item--on" : ""}`}
                  onClick={() => {
                    setSelected(l.name);
                    setPanelOpen(false);
                  }}
                >
                  {l.name}
                </button>
              </li>
            ))}
            {!filtered.length && <li className="mv-empty">No lecturers match.</li>}
          </ul>
        </aside>

        <main className="mv-grid-wrap">
          {loading && <p className="mv-empty">Loading…</p>}
          {!loading && !week && <p className="mv-empty">Choose a lecturer to see their week.</p>}
          {!loading && week && <MobileWeekGrid week={week} />}
        </main>
      </div>
    </div>
  );
}

function StaleIndicator({ week, onRefresh }: { week: LecturerWeek; onRefresh: () => void }) {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => {
      setOnline(true);
      onRefresh();
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [onRefresh]);

  if (online && !week.fromCache) return null;
  const when = week.cachedAt ? new Date(week.cachedAt) : null;
  return (
    <span className="mv-stale" role="status">
      Offline · last updated{" "}
      {when
        ? when.toLocaleString(undefined, {
            weekday: "short",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "unknown"}
    </span>
  );
}

function MobileLogin({ onSignedIn }: { onSignedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login({ username: username.trim(), password });
      setToken(res.access_token);
      onSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mv-login">
      <form className="mv-login-card" onSubmit={submit}>
        <h1>TAFEtabler</h1>
        <p className="mv-login-hint">Sign in to view timetables.</p>
        <input
          className="mv-input"
          placeholder="Username"
          autoCapitalize="none"
          autoCorrect="off"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className="mv-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="mv-error">{error}</div>}
        <button className="mv-signin" type="submit" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

export { minutesToLabel, slotToMinutes };
