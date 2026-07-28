/** "Get it on your phone" — the /m link, a scannable QR, and install steps.
 *
 * The QR is rendered locally from the URL; it is never sent to a third-party
 * chart service, so internal timetable URLs stay inside the deployment. */
import { useMemo, useState } from "react";
import qrcode from "qrcode-generator";

function qrSvg(text: string, size = 148): string {
  // Type 0 = pick the smallest version that fits; "M" tolerates a little
  // screen glare and printing.
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const cell = size / count;
  let path = "";
  for (let r = 0; r < count; r++) {
    for (let c = 0; c < count; c++) {
      if (qr.isDark(r, c)) {
        path += `M${(c * cell).toFixed(2)},${(r * cell).toFixed(2)}h${cell.toFixed(2)}v${cell.toFixed(2)}h-${cell.toFixed(2)}z`;
      }
    }
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" ` +
    `viewBox="0 0 ${size} ${size}" role="img" aria-label="QR code linking to the phone app">` +
    `<rect width="${size}" height="${size}" fill="#ffffff"/>` +
    `<path d="${path}" fill="#000000"/></svg>`
  );
}

export function PhoneAppCard({ bare = false }: { bare?: boolean } = {}) {
  const [copied, setCopied] = useState(false);
  const url = useMemo(() => `${window.location.origin}/m`, []);
  const svg = useMemo(() => {
    try {
      return qrSvg(url);
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
