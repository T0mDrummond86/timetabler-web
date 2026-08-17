import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { FormEvent, useEffect, useState } from "react";
import { api, getToken, setDeviceToken, setToken } from "./api";
import { AppShell } from "./components/AppShell";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { TwoFactorSetupPage } from "./pages/TwoFactorSetupPage";

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
const SessionSettingsPage = lazy(() =>
  import("./pages/SessionSettingsPage").then((m) => ({ default: m.SessionSettingsPage })),
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
  // Signing in is two steps once two-factor is on: the password, then a code.
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(true);

  async function finishSignIn(accessToken: string) {
    setToken(accessToken);
    const me = await api.me();
    navigate(me.must_change_password ? "/change-password" : "/dashboard");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.login({ username, password });
      if (res.mfa_setup_required && res.pending_token) {
        // Never enrolled. Enrolment is mandatory, so this is the only way on.
        navigate("/two-factor-setup", {
          replace: true,
          state: { pendingToken: res.pending_token },
        });
        return;
      }
      if (res.mfa_required && res.pending_token) {
        setPendingToken(res.pending_token);
        return;
      }
      if (res.access_token) {
        // A trusted device, or enforcement switched off on the host.
        await finishSignIn(res.access_token);
        return;
      }
      setError("Unexpected sign-in response. Try again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    if (!pendingToken) return;
    setError(null);
    setLoading(true);
    try {
      const res = await api.mfaVerify({
        pending_token: pendingToken,
        code,
        remember_device: rememberDevice,
        device_label: navigator.userAgent.slice(0, 120),
      });
      // On a verify, pending_token carries the remember-this-device marker.
      if (res.pending_token) setDeviceToken(res.pending_token);
      if (res.access_token) await finishSignIn(res.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code was not accepted");
      setCode("");
    } finally {
      setLoading(false);
    }
  }

  if (pendingToken) {
    return (
      <AppShell minimal>
        <div className="auth-page">
          <div className="card auth-card">
            <h1>Enter your code</h1>
            <p className="muted">
              Open your authenticator app and enter the six-digit code for TAFEtabler. You can
              also use one of your recovery codes.
            </p>
            <form className="form" onSubmit={onVerify}>
              <label>
                Code
                <input
                  autoFocus
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={rememberDevice}
                  onChange={(e) => setRememberDevice(e.target.checked)}
                />
                Remember this device for 30 days
              </label>
              {error && <p className="error">{error}</p>}
              <button
                type="submit"
                className="btn-primary"
                disabled={loading || !code.trim()}
                style={{ width: "100%" }}
              >
                {loading ? "Checking…" : "Sign in"}
              </button>
            </form>
            <button
              type="button"
              className="tutorial-link"
              style={{ marginTop: "0.75rem" }}
              onClick={() => {
                setPendingToken(null);
                setCode("");
                setError(null);
              }}
            >
              Back
            </button>
          </div>
        </div>
      </AppShell>
    );
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
      <Route path="/two-factor-setup" element={<TwoFactorSetupPage />} />
      <Route path="/account/password" element={<ChangePasswordPage voluntary />} />
      <Route path="/register" element={<Navigate to="/login" replace />} />
      <Route path="/m" element={<MobilePage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/global/:globalSessionId" element={<GlobalSessionPage />} />
      <Route path="/timetable/:sessionId" element={<TimetablePage />} />
      <Route path="/timetable/:sessionId/settings" element={<SessionSettingsPage />} />
      <Route path="/timetable/:sessionId/split" element={<TimetableSplitPage />} />
    </Routes>
    </Suspense>
  );
}
