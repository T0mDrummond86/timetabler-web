import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { APP_NAME } from "../branding";
import { ThemeToggle } from "./ThemeToggle";

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
    </div>
  );
}
