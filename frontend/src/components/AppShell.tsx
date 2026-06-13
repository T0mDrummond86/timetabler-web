import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { APP_NAME } from "../branding";
import { useTheme } from "../lib/theme";
import lockupLight from "../assets/brand/lockup-light.svg";
import lockupDark from "../assets/brand/lockup-dark.svg";
import { ThemeToggle } from "./ThemeToggle";

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
}: Props) {
  const theme = useTheme();
  const lockup = theme === "dark" ? lockupDark : lockupLight;
  return (
    <div className={`app-shell${fillViewport ? " app-shell--fill" : ""}`}>
      {!minimal && (
        <header className="app-topbar">
          <div className="app-topbar-start">
            <Link to="/dashboard" className="app-brand" aria-label={APP_NAME}>
              <img src={lockup} alt={APP_NAME} className="app-brand-lockup" />
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
