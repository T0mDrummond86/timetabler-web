import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { FormEvent, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";
import { AppShell } from "./components/AppShell";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";

// Every heavy page is code-split, so a phone opening /m downloads the mobile
// viewer and the shell — never the desktop timetable editor.
const MobilePage = lazy(() => import("./mobile/MobilePage"));
const AdminPage = lazy(() => import("./pages/AdminPage").then((m) => ({ default: m.AdminPage })));
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const GlobalSessionPage = lazy(() =>
  import("./pages/GlobalSessionPage").then((m) => ({ default: m.GlobalSessionPage })),
);
const TimetablePage = lazy(() =>
  import("./pages/TimetablePage").then((m) => ({ default: m.TimetablePage })),
);
const TimetableSplitPage = lazy(() =>
  import("./pages/TimetableSplitPage").then((m) => ({ default: m.TimetableSplitPage })),
);

function LoginForm() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.login({ username, password });
      setToken(res.access_token);
      const me = await api.me();
      navigate(me.must_change_password ? "/change-password" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell minimal>
      <div className="auth-page">
        <div className="card auth-card">
          <h1>Sign in</h1>
          <form className="form" onSubmit={onSubmit}>
            <label>
              Username
              <input
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && <p className="error">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading} style={{ width: "100%" }}>
              {loading ? "Please wait…" : "Sign in"}
            </button>
          </form>
          <p className="muted center" style={{ marginTop: "1rem" }}>
            Contact an administrator if you need an account.
          </p>
        </div>
      </div>
    </AppShell>
  );
}

function HomeRedirect() {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setTarget("/login");
      return;
    }
    void api.me().then(
      (me) => setTarget(me.must_change_password ? "/change-password" : "/dashboard"),
      () => setTarget("/login"),
    );
  }, []);

  if (!target) return null;
  return <Navigate to={target} replace />;
}

export default function App() {
  return (
    <Suspense fallback={null}>
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginForm />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />
      <Route path="/account/password" element={<ChangePasswordPage voluntary />} />
      <Route path="/register" element={<Navigate to="/login" replace />} />
      <Route path="/m" element={<MobilePage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/global/:globalSessionId" element={<GlobalSessionPage />} />
      <Route path="/timetable/:sessionId" element={<TimetablePage />} />
      <Route path="/timetable/:sessionId/split" element={<TimetableSplitPage />} />
    </Routes>
    </Suspense>
  );
}
