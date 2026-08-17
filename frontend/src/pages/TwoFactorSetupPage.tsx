/** Two-factor enrolment: scan, confirm, keep the recovery codes.
 *
 * Reached with the setup token a sign-in hands out when the account has never
 * enrolled — an unenrolled user has no session to authenticate with, so the
 * pending token is the only thing carrying them here.
 *
 * Three states in one screen, because they are one task: show the secret,
 * take a code, then show the recovery codes and refuse to move on until the
 * user says they have saved them.
 */
import { FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { LoadingMark } from "../components/LoadingMark";
import { api, setToken, type MfaSetup } from "../api";
import { qrSvgMarkup } from "../lib/qrSvg";

export function TwoFactorSetupPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const pendingToken = (location.state as { pendingToken?: string } | null)?.pendingToken;

  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pendingToken) {
      // Arrived without a token — a refresh, or a stale link. Signing in again
      // is the only way to get one, and it takes two seconds.
      navigate("/login", { replace: true });
      return;
    }
    let cancelled = false;
    void api
      .mfaSetup(pendingToken)
      .then((data) => {
        if (!cancelled) setSetup(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not start setup");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pendingToken, navigate]);

  async function onConfirm(e: FormEvent) {
    e.preventDefault();
    if (!pendingToken) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.mfaConfirm(pendingToken, code);
      // Hold the session but stay here: the recovery codes are shown once, and
      // navigating away before the user has them would be losing them.
      setToken(result.access_token);
      setRecoveryCodes(result.recovery_codes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code was not accepted");
    } finally {
      setBusy(false);
    }
  }

  function downloadCodes() {
    if (!recoveryCodes) return;
    const body =
      `TAFEtabler recovery codes — ${setup?.username ?? ""}\n\n` +
      `Each code works once, in place of your authenticator code.\n` +
      `Keep them somewhere other than your phone.\n\n` +
      recoveryCodes.join("\n") +
      "\n";
    const blob = new Blob([body], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tafetabler-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (recoveryCodes) {
    return (
      <AppShell minimal>
        <div className="auth-page">
          <div className="card auth-card auth-card-wide">
            <h1>Save your recovery codes</h1>
            <p className="muted">
              Two-factor is now on. These ten codes are your way in if you lose your phone —
              each works once, and this is the only time they are shown. Print them or save
              them somewhere that is not the phone itself.
            </p>
            <ul className="recovery-code-list">
              {recoveryCodes.map((c) => (
                <li key={c}>
                  <code>{c}</code>
                </li>
              ))}
            </ul>
            <div className="row gap">
              <button type="button" className="btn-secondary" onClick={downloadCodes}>
                Download as a text file
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void navigator.clipboard.writeText(recoveryCodes.join("\n"))}
              >
                Copy
              </button>
            </div>
            <p className="muted" style={{ marginTop: "1rem" }}>
              Lost them later? An administrator can reset your two-factor and you can set it
              up again.
            </p>
            <button
              type="button"
              className="btn-primary"
              style={{ width: "100%", marginTop: "0.5rem" }}
              onClick={() => navigate("/dashboard", { replace: true })}
            >
              I have saved these — continue
            </button>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell minimal>
      <div className="auth-page">
        <div className="card auth-card auth-card-wide">
          <h1>Set up two-factor sign-in</h1>
          <p className="muted">
            Timetables name where every lecturer is for a term, so signing in takes a code as
            well as a password. You need an authenticator app — Microsoft Authenticator, Google
            Authenticator and 1Password all work.
          </p>

          {error && <p className="error">{error}</p>}

          {!setup && !error ? (
            <LoadingMark label="Preparing…" />
          ) : setup ? (
            <>
              <ol className="totp-steps">
                <li>
                  <strong>Scan this with your authenticator app.</strong>
                  <div
                    className="totp-qr"
                    aria-label="Two-factor setup QR code"
                    dangerouslySetInnerHTML={{ __html: qrSvgMarkup(setup.provisioning_uri, 176) }}
                  />
                  <p className="muted">
                    Can&rsquo;t scan? Enter this key by hand:
                    <br />
                    <code className="totp-secret">{setup.secret}</code>
                  </p>
                </li>
                <li>
                  <strong>Enter the six-digit code it shows.</strong>
                  <form className="form" onSubmit={onConfirm}>
                    <label>
                      Code
                      <input
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        placeholder="123456"
                        required
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                      />
                    </label>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={busy || code.trim().length < 6}
                      style={{ width: "100%" }}
                    >
                      {busy ? "Checking…" : "Turn on two-factor"}
                    </button>
                  </form>
                </li>
              </ol>
            </>
          ) : null}
        </div>
      </div>
    </AppShell>
  );
}
