/** Per-session settings: delivery mode, displayed teaching day, who can edit,
 *  the phone app, and the destructive actions. Reached from the session's ⋯
 *  menu on the dashboard. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type AccessLevel,
  type SessionAccessList,
  type SessionMode,
  type TimetableSession,
} from "../api";
import { AppShell } from "../components/AppShell";
import { PhoneAppCard } from "../components/PhoneAppCard";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";

const MODES: { value: SessionMode; label: string; hint: string }[] = [
  {
    value: "hybrid",
    label: "Hybrid",
    hint: "Both families of views, with a Regular/Block selector in the timetable sidebar.",
  },
  {
    value: "regular",
    label: "Regular only",
    hint: "Courses, Staff, Rooms, Day and Unassigned lecturer. No mode selector.",
  },
  {
    value: "block",
    label: "Block only",
    hint: "Block delivery and Block groups. No mode selector.",
  },
];

const NUM_SLOTS = 28;
const SLOT_MINUTES = 30;
const FIRST_SLOT_MINUTES = 8 * 60;

function slotLabel(slot: number): string {
  const mins = FIRST_SLOT_MINUTES + slot * SLOT_MINUTES;
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
}

export function SessionSettingsPage() {
  const { sessionId: idParam } = useParams();
  const sessionId = Number(idParam);
  const navigate = useNavigate();
  const { confirm, dialogs } = useConfirmPrompt();

  const [session, setSession] = useState<TimetableSession | null>(null);
  const [access, setAccess] = useState<SessionAccessList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, a] = await Promise.all([
        api.session(sessionId),
        api.sessionAccess(sessionId).catch(() => null),
      ]);
      setSession(s);
      setAccess(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this session");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const readOnly = (session?.access_level ?? "edit") !== "edit";

  async function run(key: string, fn: () => Promise<unknown>, ok?: string) {
    setSaving(key);
    setError(null);
    setNote(null);
    try {
      await fn();
      await load();
      if (ok) setNote(ok);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That change could not be saved");
    } finally {
      setSaving(null);
    }
  }

  const startSlot = session?.grid_start_slot ?? 0;
  const endSlot = session?.grid_end_slot ?? NUM_SLOTS;
  const windowSet = session?.grid_start_slot != null || session?.grid_end_slot != null;

  const slotOptions = useMemo(
    () => Array.from({ length: NUM_SLOTS }, (_, i) => i),
    [],
  );

  if (loading) {
    return (
      <AppShell breadcrumb={<Link to="/dashboard">Dashboard</Link>} title="Settings">
        <p className="panel-empty">Loading…</p>
      </AppShell>
    );
  }

  if (!session) {
    return (
      <AppShell breadcrumb={<Link to="/dashboard">Dashboard</Link>} title="Settings">
        <div className="error-banner">{error ?? "Session not found"}</div>
      </AppShell>
    );
  }

  return (
    <AppShell
      breadcrumb={
        <>
          <Link to="/dashboard">Dashboard</Link>
          <span aria-hidden> / </span>
          <Link to={`/timetable/${sessionId}`}>{session.name}</Link>
        </>
      }
      title="Settings"
      subtitle={<span className="muted">{session.name}</span>}
    >
      {error && <div className="error-banner">{error}</div>}
      {note && <div className="success-banner">{note}</div>}
      {readOnly && (
        <div className="settings-readonly">
          You have read-only access to this session, so these settings cannot be changed.
        </div>
      )}

      <section className="card settings-card">
        <h2>Delivery mode</h2>
        <p className="muted entity-hint">
          Controls which timetable views this session offers. Changing it never alters any
          scheduled class — only what you can look at.
        </p>
        <div className="settings-modes">
          {MODES.map((m) => (
            <label
              key={m.value}
              className={`settings-mode${(session.timetable_mode ?? "hybrid") === m.value ? " settings-mode--on" : ""}`}
            >
              <input
                type="radio"
                name="timetable-mode"
                value={m.value}
                checked={(session.timetable_mode ?? "hybrid") === m.value}
                disabled={readOnly || saving === "mode"}
                onChange={() =>
                  void run(
                    "mode",
                    () => api.sessionSettings(sessionId, { timetable_mode: m.value }),
                    `Mode set to ${m.label}.`,
                  )
                }
              />
              <span className="settings-mode-label">{m.label}</span>
              <span className="settings-mode-hint muted">{m.hint}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="card settings-card">
        <h2>Teaching day</h2>
        <p className="muted entity-hint">
          Narrow the hours the grid shows. A tighter day makes every timetable denser on
          screen and on a phone. A class already placed outside the window will block the
          change rather than disappear.
        </p>
        <div className="settings-row">
          <label className="settings-field">
            Starts
            <select
              className="field-select"
              value={startSlot}
              disabled={readOnly || saving === "window"}
              onChange={(e) =>
                void run(
                  "window",
                  () =>
                    api.sessionSettings(sessionId, {
                      grid_start_slot: Number(e.target.value),
                      grid_end_slot: endSlot,
                    }),
                  "Teaching day updated.",
                )
              }
            >
              {slotOptions.map((s) => (
                <option key={s} value={s}>
                  {slotLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="settings-field">
            Ends
            <select
              className="field-select"
              value={endSlot}
              disabled={readOnly || saving === "window"}
              onChange={(e) =>
                void run(
                  "window",
                  () =>
                    api.sessionSettings(sessionId, {
                      grid_start_slot: startSlot,
                      grid_end_slot: Number(e.target.value),
                    }),
                  "Teaching day updated.",
                )
              }
            >
              {slotOptions.map((s) => s + 1).map((s) => (
                <option key={s} value={s}>
                  {slotLabel(s)}
                </option>
              ))}
            </select>
          </label>
          {windowSet && (
            <button
              type="button"
              className="btn-secondary btn-xs"
              disabled={readOnly || saving === "window"}
              onClick={() =>
                void run(
                  "window",
                  () => api.sessionSettings(sessionId, { clear_grid_window: true }),
                  "Teaching day reset to the full span.",
                )
              }
            >
              Reset to full day
            </button>
          )}
          {!windowSet && <span className="muted">Showing the full day (08:00–22:00).</span>}
        </div>
      </section>

      <section className="card settings-card">
        <h2>Who can edit this session</h2>
        {access && access.global_session_id == null && (
          <p className="muted entity-hint">
            This session isn't linked to a global workspace, so access follows each person's
            organisation role. Link it to a workspace to set per-person access.
          </p>
        )}
        {access && access.global_session_id != null && !access.can_manage && (
          <p className="muted entity-hint">
            Only the workspace owner can change these. This shows what each person can do here.
          </p>
        )}
        {access && !!access.users.length && (
          <div className="access-table-wrap">
            <table className="access-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Can do</th>
                  <th>Because</th>
                  {access.can_manage && <th>Override for this session</th>}
                </tr>
              </thead>
              <tbody>
                {access.users.map((u) => {
                  const fixed = ["admin", "org owner", "creator"].includes(u.source);
                  return (
                    <tr key={u.user_id}>
                      <td>
                        <span className="access-user">{u.name || u.username}</span>
                        <span className="access-username muted">{u.username}</span>
                      </td>
                      <td>{u.level === "edit" ? "Edit" : "Read-only"}</td>
                      <td className="muted">{u.source}</td>
                      {access.can_manage && (
                        <td>
                          {fixed ? (
                            <span className="access-pill access-pill--fixed">Always edit</span>
                          ) : (
                            <select
                              className="field-select"
                              value={u.override ?? ""}
                              disabled={saving === `acc-${u.user_id}`}
                              onChange={(e) =>
                                void run(`acc-${u.user_id}`, () =>
                                  e.target.value === ""
                                    ? api.clearSessionAccessLevel(sessionId, u.user_id)
                                    : api.setSessionAccessLevel(
                                        sessionId,
                                        u.user_id,
                                        e.target.value as AccessLevel,
                                      ),
                                )
                              }
                            >
                              <option value="">No override</option>
                              <option value="edit">Edit</option>
                              <option value="read_only">Read-only</option>
                            </select>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card settings-card">
        <h2>Timetables on your phone</h2>
        <PhoneAppCard bare />
      </section>

      <section className="card settings-card settings-danger">
        <h2>Danger zone</h2>
        <div className="settings-danger-rows">
          <DangerRow
            title="Rename this session"
            body="Changes the name everywhere, including exports."
            action="Rename…"
            disabled={readOnly}
            onClick={async () => {
              const name = window.prompt("New session name", session.name)?.trim();
              if (!name || name === session.name) return;
              await run("rename", () => api.patchSession(sessionId, name), "Renamed.");
            }}
          />
          <DangerRow
            title="Duplicate this session"
            body="Creates a full copy. The change log is not carried over."
            action="Duplicate…"
            disabled={readOnly}
            onClick={async () => {
              const name = window.prompt("Name for the copy", `${session.name} copy`)?.trim();
              if (!name) return;
              setSaving("dup");
              setError(null);
              try {
                const copy = await api.duplicateSession(sessionId, name);
                navigate(`/timetable/${copy.id}`);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Duplicate failed");
              } finally {
                setSaving(null);
              }
            }}
          />
          <DangerRow
            title="Delete this session"
            body="Permanently removes every class, room, lecturer and log entry in it."
            action="Delete"
            danger
            disabled={readOnly}
            onClick={async () => {
              if (
                !(await confirm({
                  title: "Delete session",
                  message: `Delete “${session.name}”? All timetable data in this session will be permanently removed.`,
                  confirmLabel: "Delete",
                  danger: true,
                }))
              )
                return;
              setSaving("del");
              try {
                await api.deleteSession(sessionId);
                navigate("/dashboard");
              } catch (err) {
                setError(err instanceof Error ? err.message : "Delete failed");
                setSaving(null);
              }
            }}
          />
        </div>
      </section>
      {dialogs}
    </AppShell>
  );
}

function DangerRow({
  title,
  body,
  action,
  onClick,
  danger,
  disabled,
}: {
  title: string;
  body: string;
  action: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="settings-danger-row">
      <div>
        <strong>{title}</strong>
        <p className="muted">{body}</p>
      </div>
      <button
        type="button"
        className={danger ? "btn-danger" : "btn-secondary"}
        disabled={disabled}
        title={disabled ? "Read-only access to this session" : undefined}
        onClick={onClick}
      >
        {action}
      </button>
    </div>
  );
}
