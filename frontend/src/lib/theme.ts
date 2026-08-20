import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "timetabler-theme";

export function getStoredTheme(): Theme {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "dark" || value === "light") return value;
  } catch {
    /* ignore */
  }
  // Dark is the default for anyone who has not chosen. A stored preference
  // always wins, so this only affects a first visit.
  return "dark";
}

/** Matches --bg in each theme, so the PWA's browser chrome and iOS status
 *  bar sit flush with the page instead of the old fixed blue. */
const THEME_COLOUR: Record<Theme, string> = { light: "#e3e6ec", dark: "#0f172a" };

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLOUR[theme]);
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
  applyTheme(theme);
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}

function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export function useTheme(): Theme {
  const [theme, setLocal] = useState<Theme>(() =>
    typeof document === "undefined" ? "dark" : currentTheme(),
  );
  useEffect(() => {
    setLocal(currentTheme());
    const observer = new MutationObserver(() => setLocal(currentTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}
