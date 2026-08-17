/** "Get it on your phone" — the /m link, a scannable QR, and install steps.
 *
 * The QR is rendered locally from the URL; it is never sent to a third-party
 * chart service, so internal timetable URLs stay inside the deployment. */
import { useMemo, useState } from "react";
import { qrSvgMarkup } from "../lib/qrSvg";

export function PhoneAppCard({ bare = false }: { bare?: boolean } = {}) {
  const [copied, setCopied] = useState(false);
  const url = useMemo(() => `${window.location.origin}/m`, []);
  const svg = useMemo(() => {
    try {
      return qrSvgMarkup(url);
    } catch {
      return null;
    }
  }, [url]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      /* the link is on screen anyway */
    }
  }

  return (
    <section className={`phone-app-card${bare ? " phone-app-card--bare" : ""}`}>
      <div className="phone-app-text">
        {!bare && <h3>Timetables on your phone</h3>}
        <p className="muted">
          A read-only viewer for lecturer timetables across this workspace. Scan the code
          with a phone camera, or open <code>{url}</code>, then add it to the home screen —
          it opens full-screen like an app and keeps working in a dead spot.
        </p>
        <ol className="phone-app-steps muted">
          <li>
            <strong>iPhone:</strong> open in Safari → Share → Add to Home Screen
          </li>
          <li>
            <strong>Android:</strong> open in Chrome → menu → Install app
          </li>
        </ol>
        <div className="phone-app-actions">
          <a className="btn-secondary btn-xs" href="/m" target="_blank" rel="noreferrer">
            Open the phone view
          </a>
          <button type="button" className="btn-secondary btn-xs" onClick={() => void copyLink()}>
            {copied ? "Copied ✓" : "Copy link"}
          </button>
        </div>
      </div>
      {svg && (
        <div
          className="phone-app-qr"
          /* Locally generated markup, no user input in the path data. */
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}
    </section>
  );
}
