import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";

type Props = {
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
  wide?: boolean;
  minimal?: boolean;
};

export function AppShell({
  children,
  title,
  subtitle,
  breadcrumb,
  actions,
  wide = false,
  minimal = false,
}: Props) {
  return (
    <div className="app-shell">
      {!minimal && (
        <header className="app-topbar">
          <div className="app-topbar-start">
            <Link to="/dashboard" className="app-brand">
              Timetabler
            </Link>
          </div>
          <div className="app-topbar-end">
            <ThemeToggle />
            {actions}
          </div>
        </header>
      )}

      <main className={`app-main${wide ? " app-main-wide" : ""}`}>
        {!minimal && (breadcrumb || title) && (
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
