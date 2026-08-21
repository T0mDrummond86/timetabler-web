import { Link } from "react-router-dom";
import { Suspense, lazy, useEffect, useState, type ReactNode } from "react";
import { APP_NAME } from "../branding";
import { ThemeToggle } from "./ThemeToggle";

// The help panel carries an embedding model behind it, so it is never part of
// the main bundle -- nothing is fetched until someone actually asks for help.
const HelpPanel = lazy(() => import("../help/HelpPanel"));

function HelpButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      className="btn-secondary btn-xs help-open"
      onClick={onOpen}
      aria-label="Help"
      title="Help — search for how to do something"
    >
      ?
    </button>
  );
}

// The same file the browser tab and the installed app use, referenced rather
// than copied so the three can never drift apart. Its squares sit on a
// transparent ground, so one asset serves both themes.
const BRAND_MARK = "/favicon.svg";

type Props = {
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
  wide?: boolean;
  minimal?: boolean;
  /** Lock shell to viewport height (timetable grid + scrollable sidebar). */
  fillViewport?: boolean;
  /** Fold the brand bar, breadcrumb, title and subtitle into one slim bar —
   *  used by working screens where vertical space belongs to the content. */
  compact?: boolean;
};

export function AppShell({
  children,
  title,
  subtitle,
  breadcrumb,
  actions,
  wide = false,
  minimal = false,
  fillViewport = false,
  compact = false,
}: Props) {
  const [helpOpen, setHelpOpen] = useState(false);

  // "?" from anywhere that is not a text field, the way most tools do it.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (minimal) return;
      if (e.key !== "?" || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = document.activeElement;
      const typing =
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement ||
        (el instanceof HTMLElement && el.isContentEditable);
      if (typing) return;
      e.preventDefault();
      setHelpOpen(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [minimal]);

  return (
    <div className={`app-shell${fillViewport ? " app-shell--fill" : ""}`}>
      {!minimal && compact && (
        <header className="app-topbar app-topbar--compact">
          <Link to="/dashboard" className="app-brand" aria-label={`${APP_NAME} — dashboard`}>
            <img src={BRAND_MARK} alt={APP_NAME} className="app-brand-mark app-brand-mark--sm" />
          </Link>
          {breadcrumb && <span className="topbar-crumb">{breadcrumb}</span>}
          {breadcrumb && title && (
            <span className="topbar-crumb-sep" aria-hidden>
              /
            </span>
          )}
          {title && <span className="topbar-title">{title}</span>}
          {subtitle && <span className="topbar-subtitle">{subtitle}</span>}
          <span className="topbar-spacer" />
          {actions}
          <HelpButton onOpen={() => setHelpOpen(true)} />
          <ThemeToggle />
        </header>
      )}
      {!minimal && !compact && (
        <header className="app-topbar">
          <div className="app-topbar-start">
            <Link to="/dashboard" className="app-brand" aria-label={APP_NAME}>
              <img src={BRAND_MARK} alt={APP_NAME} className="app-brand-mark" />
            </Link>
          </div>
          <div className="app-topbar-end">
            <HelpButton onOpen={() => setHelpOpen(true)} />
            <ThemeToggle />
            {actions}
          </div>
        </header>
      )}

      <main
        className={`app-main${wide ? " app-main-wide" : ""}${fillViewport ? " app-main--fill" : ""}`}
      >
        {!minimal && !compact && (breadcrumb || title) && (
          <div className="page-head">
            {breadcrumb && <div className="page-breadcrumb">{breadcrumb}</div>}
            {title && <h1 className="page-title">{title}</h1>}
            {subtitle && <p className="page-subtitle">{subtitle}</p>}
          </div>
        )}
        {children}
      </main>

      {helpOpen && (
        <Suspense fallback={null}>
          <HelpPanel onClose={() => setHelpOpen(false)} />
        </Suspense>
      )}
    </div>
  );
}
