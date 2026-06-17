import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getToken } from "../api";
import { AppShell } from "../components/AppShell";

type ChangePasswordPageProps = {
  /** Allow signed-in users to change password voluntarily (not only on first sign-in). */
  voluntary?: boolean;
};

export function ChangePasswordPage({ voluntary = false }: ChangePasswordPageProps) {
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    void (async () => {
      try {
        const me = await api.me();
        setUsername(me.username);
        if (!voluntary && !me.must_change_password) {
          navigate("/dashboard");
        }
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    })();
  }, [navigate, voluntary]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      navigate(voluntary ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password");
    } finally {
      setSaving(false);
    }
  }

  const form = (
    <form className="form" onSubmit={(e) => void onSubmit(e)}>
      <label>
        {voluntary ? "Current password" : "Current (temporary) password"}
        <input
          type="password"
          required
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
      </label>
      <label>
        New password
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </label>
      <label>
        Confirm new password
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" className="btn-primary" disabled={saving} style={{ width: "100%" }}>
        {saving ? "Saving…" : voluntary ? "Update password" : "Save and continue"}
      </button>
    </form>
  );

  if (loading) {
    return (
      <AppShell minimal>
        <p className="muted center">Loading…</p>
      </AppShell>
    );
  }

  if (voluntary) {
    return (
      <AppShell
        title="Change password"
        subtitle={username ? `Signed in as ${username}` : undefined}
        breadcrumb={
          <>
            <Link to="/dashboard">Dashboard</Link>
            <span aria-hidden> / </span>
            <Link to="/admin">Admin</Link>
            <span aria-hidden> / </span>
            Change password
          </>
        }
        actions={
          <button type="button" className="btn-secondary" onClick={() => navigate("/admin")}>
            Cancel
          </button>
        }
      >
        <section className="card dashboard-card" style={{ maxWidth: "28rem" }}>
          <h2>Update your password</h2>
          <p className="muted">Enter your current password, then choose a new one (at least 8 characters).</p>
          {form}
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell minimal>
      <div className="auth-page">
        <div className="card auth-card">
          <h1>Set your password</h1>
          <p className="muted">
            Your account uses a temporary password. Choose a new password before continuing.
          </p>
          {form}
        </div>
      </div>
    </AppShell>
  );
}
