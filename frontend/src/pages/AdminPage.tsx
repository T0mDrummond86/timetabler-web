import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, AdminUser, getToken, GlobalSessionAccess, GlobalSessionSummary } from "../api";
import { AppShell } from "../components/AppShell";
import { LoadingMark } from "../components/LoadingMark";

const DEFAULT_USER_PASSWORD = "tafetabler";

export function AdminPage() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [globalSessions, setGlobalSessions] = useState<GlobalSessionSummary[]>([]);
  const [selectedGlobalId, setSelectedGlobalId] = useState<number | null>(null);
  const [globalAccess, setGlobalAccess] = useState<GlobalSessionAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    void load();
  }, [navigate]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const me = await api.me();
      if (!me.is_admin) {
        navigate("/dashboard");
        return;
      }
      const orgs = await api.orgs();
      if (!orgs.length) throw new Error("No organization");
      const [u, g] = await Promise.all([api.adminUsers(), api.globalSessions(orgs[0].id)]);
      setUsers(u);
      setGlobalSessions(g);
      if (g.length && selectedGlobalId == null) {
        setSelectedGlobalId(g[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
      if (err instanceof Error && err.message.includes("403")) {
        navigate("/dashboard");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (selectedGlobalId == null) {
      setGlobalAccess([]);
      return;
    }
    void (async () => {
      try {
        const rows = await api.adminGlobalAccess(selectedGlobalId);
        setGlobalAccess(rows);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load global access");
      }
    })();
  }, [selectedGlobalId]);

  async function createUser(e: FormEvent) {
    e.preventDefault();
    if (!newUsername.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const row = await api.adminCreateUser({
        username: newUsername.trim(),
        password: DEFAULT_USER_PASSWORD,
        name: newName.trim(),
      });
      setUsers((prev) => [...prev, row].sort((a, b) => a.username.localeCompare(b.username)));
      setNewUsername("");
      setNewName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(user: AdminUser) {
    setError(null);
    try {
      const updated = await api.adminPatchUser(user.id, { is_active: !user.is_active });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function resetPassword(user: AdminUser) {
    setError(null);
    try {
      const updated = await api.adminPatchUser(user.id, { password: DEFAULT_USER_PASSWORD });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    }
  }

  async function deleteUser(user: AdminUser) {
    if (!window.confirm(`Delete user ${user.username}? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.adminDeleteUser(user.id);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
      if (selectedGlobalId != null) {
        setGlobalAccess((prev) => prev.filter((row) => row.user_id !== user.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function toggleGlobalAccess(userId: number) {
    if (selectedGlobalId == null) return;
    const allowed = new Set(globalAccess.map((a) => a.user_id));
    if (allowed.has(userId)) allowed.delete(userId);
    else allowed.add(userId);
    setError(null);
    try {
      const rows = await api.adminSetGlobalAccess(selectedGlobalId, [...allowed]);
      setGlobalAccess(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Access update failed");
    }
  }

  const accessIds = new Set(globalAccess.map((a) => a.user_id));

  return (
    <AppShell
      title="Administration"
      subtitle="Create user accounts and grant access to global workspaces."
      breadcrumb={
        <>
          <Link to="/dashboard">Dashboard</Link>
          <span aria-hidden> / </span>
          Admin
        </>
      }
      actions={
        <>
          <Link to="/account/password" className="btn-secondary">
            Change password
          </Link>
          <button type="button" className="btn-secondary" onClick={() => navigate("/dashboard")}>
            Back to dashboard
          </button>
        </>
      }
    >
      {error && <div className="error-banner">{error}</div>}
      {loading ? (
        <LoadingMark label="Loading…" />
      ) : (
        <>
          <section className="card dashboard-card">
            <h2>Users</h2>
            <p className="muted">
              New users are created with default password <code>{DEFAULT_USER_PASSWORD}</code> and
              must change it on first sign-in.
            </p>
            <form className="dashboard-create-form" onSubmit={(e) => void createUser(e)}>
              <input
                className="field-input"
                placeholder="Username"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                required
                autoComplete="off"
              />
              <input
                className="field-input"
                placeholder="Display name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <button type="submit" className="btn-primary" disabled={creating}>
                {creating ? "Creating…" : "Create user"}
              </button>
            </form>
            <ul className="session-list dashboard-session-list">
              {users
                .filter((u) => !u.is_admin)
                .map((u) => (
                  <li key={u.id} className="dashboard-session-row">
                    <div className="dashboard-session-main">
                      <div className="dashboard-session-title">
                        <strong>{u.username}</strong>
                        {!u.is_active && <span className="session-badge">Disabled</span>}
                        {u.must_change_password && (
                          <span className="session-badge session-badge--global">Password not set</span>
                        )}
                      </div>
                      <span className="muted dashboard-session-meta">
                        {u.name || "—"} · {u.role}
                      </span>
                    </div>
                    <div className="row gap">
                      <button
                        type="button"
                        className="btn-secondary btn-xs"
                        onClick={() => void resetPassword(u)}
                      >
                        Reset password
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-xs"
                        onClick={() => void toggleActive(u)}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-xs"
                        onClick={() => void deleteUser(u)}
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          </section>

          <section className="card dashboard-card">
            <h2>Global workspace access</h2>
            <p className="muted">
              Only users checked below can open the selected global workspace. Admins always have
              access to all global workspaces.
            </p>
            {globalSessions.length === 0 ? (
              <p className="muted panel-empty">Create a global workspace from the dashboard first.</p>
            ) : (
              <>
                <label className="dashboard-sort">
                  <span className="muted">Global workspace</span>
                  <select
                    className="field-select"
                    value={selectedGlobalId ?? ""}
                    onChange={(e) => setSelectedGlobalId(Number(e.target.value))}
                  >
                    {globalSessions.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                      </option>
                    ))}
                  </select>
                </label>
                <ul className="session-list dashboard-session-list">
                  {users
                    .filter((u) => !u.is_admin)
                    .map((u) => (
                      <li key={u.id} className="dashboard-session-row">
                        <label className="checkbox dashboard-session-main">
                          <input
                            type="checkbox"
                            checked={accessIds.has(u.id)}
                            disabled={!u.is_active}
                            onChange={() => void toggleGlobalAccess(u.id)}
                          />
                          <span>
                            <strong>{u.username}</strong>
                            {u.name ? <span className="muted"> — {u.name}</span> : null}
                          </span>
                        </label>
                      </li>
                    ))}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </AppShell>
  );
}
