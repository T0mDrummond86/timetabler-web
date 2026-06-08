import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { FormEvent, useState } from "react";
import { api, getToken, setToken } from "./api";
import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { GlobalSessionPage } from "./pages/GlobalSessionPage";
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

function HomeRedirect() {
  return getToken() ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<AuthForm mode="login" />} />
      <Route path="/register" element={<AuthForm mode="register" />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/global/:globalSessionId" element={<GlobalSessionPage />} />
      <Route path="/timetable/:sessionId" element={<TimetablePage />} />
      <Route path="/timetable/:sessionId/split" element={<TimetableSplitPage />} />
    </Routes>
  );
}
