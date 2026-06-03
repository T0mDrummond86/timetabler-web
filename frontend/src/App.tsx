import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { FormEvent, useEffect, useState } from "react";
import { api, getToken, Organization, setToken, TimetableSession, User } from "./api";
import { AppShell } from "./components/AppShell";
import { TimetablePage } from "./pages/TimetablePage";
import { TimetableSplitPage } from "./pages/TimetableSplitPage";

function AuthForm({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res =
        mode === "register"
          ? await api.register({
              email,
              password,
              name,
              organization_name: orgName || "My organization",
            })
          : await api.login({ email, password });
      setToken(res.access_token);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <div className="auth-page">
        <div className="card auth-card">
          <h1>{mode === "register" ? "Create account" : "Sign in"}</h1>
          <form className="form" onSubmit={onSubmit}>
            <label>
              Email
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {mode === "register" && (
              <>
                <label>
                  Your name
                  <input value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label>
                  Organization name
                  <input
                    required
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="e.g. Joondalup campus"
                  />
                </label>
              </>
            )}
            {error && <p className="error">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading} style={{ width: "100%" }}>
              {loading ? "Please wait…" : mode === "register" ? "Create account" : "Sign in"}
            </button>
          </form>
        </div>
        <p className="muted center" style={{ marginTop: "1rem" }}>
          {mode === "register" ? (
            <>
              Already have an account? <Link to="/login">Sign in</Link>
            </>
          ) : (
            <>
              New here? <Link to="/register">Create account</Link>
            </>
          )}
        </p>
      </div>
    </AppShell>
  );
}

function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [sessions, setSessions] = useState<TimetableSession[]>([]);
  const [newSessionName, setNewSessionName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    (async () => {
      try {
        const [u, o] = await Promise.all([api.me(), api.orgs()]);
        setUser(u);
        setOrgs(o);
        if (o.length) {
          const s = await api.sessions(o[0].id);
          setSessions(s);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
        setToken(null);
        navigate("/login");
      }
    })();
  }, [navigate]);

  async function createSession() {
    if (!orgs.length || !newSessionName.trim()) return;
    try {
      const row = await api.createSession(orgs[0].id, newSessionName.trim());
      setSessions((prev) => [...prev, row].sort((a, b) => a.name.localeCompare(b.name)));
      setNewSessionName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  function logout() {
    setToken(null);
    navigate("/login");
  }

  const org = orgs[0];

  return (
    <AppShell
      title="Dashboard"
      subtitle={
        user
          ? `${user.name || user.email}${org ? ` · ${org.name}` : ""}`
          : undefined
      }
      actions={
        <button type="button" className="btn-secondary" onClick={logout}>
          Sign out
        </button>
      }
    >
      {error && <div className="error-banner">{error}</div>}

      <section className="card">
        <h2>Timetable sessions</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Each session is one editable timetable — like a desktop <code>.db</code> file.
        </p>
        <ul className="session-list">
          {sessions.map((s) => (
            <li key={s.id}>
              <Link to={`/timetable/${s.id}`} className="session-link">
                <strong>{s.name}</strong>
                <span className="muted">Open →</span>
              </Link>
            </li>
          ))}
          {!sessions.length && <p className="muted panel-empty">No sessions yet.</p>}
        </ul>
        <div className="inline-form">
          <input
            className="field-input"
            placeholder="New session name"
            value={newSessionName}
            onChange={(e) => setNewSessionName(e.target.value)}
          />
          <button type="button" className="btn-primary" onClick={createSession} disabled={!newSessionName.trim()}>
            Add session
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Getting started</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Open a session, import a desktop <strong>Timetable Export</strong> (.xlsm), then drag
          classes from the holding area onto the grid.
        </p>
      </section>
    </AppShell>
  );
}

function HomeRedirect() {
  return getToken() ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<AuthForm mode="login" />} />
      <Route path="/register" element={<AuthForm mode="register" />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/timetable/:sessionId" element={<TimetablePage />} />
      <Route path="/timetable/:sessionId/split" element={<TimetableSplitPage />} />
    </Routes>
  );
}
