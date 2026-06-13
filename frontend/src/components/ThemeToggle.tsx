import { toggleTheme, useTheme } from "../lib/theme";

export function ThemeToggle() {
  const theme = useTheme();

  function onToggle() {
    toggleTheme(theme);
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
