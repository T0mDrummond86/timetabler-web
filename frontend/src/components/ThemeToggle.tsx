import { useState } from "react";
import { getStoredTheme, toggleTheme, type Theme } from "../lib/theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());

  function onToggle() {
    setTheme(toggleTheme(theme));
  }

  const label = theme === "dark" ? "Light mode" : "Dark mode";

  return (
    <button
      type="button"
      className="btn-secondary btn-xs theme-toggle"
      onClick={onToggle}
      aria-label={label}
      title={label}
    >
      {theme === "dark" ? "☀ Light" : "☾ Dark"}
    </button>
  );
}
