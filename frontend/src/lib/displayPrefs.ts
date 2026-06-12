export const DISPLAY_STORAGE_KEY = "timetabler-display";

export type ClashDetectMode = "auto" | "off" | "once";

export type DisplayPrefs = {
  colourByClass: boolean;
  showAlerts: boolean;
  autoClashDetect: boolean;
};

export function readDisplayPrefs(): DisplayPrefs {
  try {
    const raw = localStorage.getItem(DISPLAY_STORAGE_KEY);
    if (!raw) {
      return { colourByClass: true, showAlerts: true, autoClashDetect: true };
    }
    const parsed = JSON.parse(raw) as Partial<DisplayPrefs>;
    return {
      colourByClass: parsed.colourByClass !== false,
      showAlerts: parsed.showAlerts !== false,
      autoClashDetect: parsed.autoClashDetect !== false,
    };
  } catch {
    return { colourByClass: true, showAlerts: true, autoClashDetect: true };
  }
}

export function writeDisplayPrefs(prefs: DisplayPrefs): void {
  localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(prefs));
}

export function clashDetectForPrefs(
  prefs: Pick<DisplayPrefs, "autoClashDetect">,
  override?: ClashDetectMode,
): ClashDetectMode {
  if (override) return override;
  return prefs.autoClashDetect ? "auto" : "off";
}
