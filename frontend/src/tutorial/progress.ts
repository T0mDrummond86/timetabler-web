/** Tutorial progress persistence (localStorage, displayPrefs pattern). */
import type { ModuleStatus, TutorialProgress } from "./types";

export const TUTORIAL_STORAGE_KEY = "timetabler-tutorial-progress";

function emptyProgress(): TutorialProgress {
  return {
    version: 1,
    active: false,
    orgId: null,
    sessionId: null,
    currentModuleId: null,
    currentStepIndex: 0,
    modules: {},
  };
}

export function readTutorialProgress(): TutorialProgress {
  try {
    const raw = localStorage.getItem(TUTORIAL_STORAGE_KEY);
    if (!raw) return emptyProgress();
    const parsed = JSON.parse(raw) as Partial<TutorialProgress>;
    if (parsed.version !== 1) return emptyProgress();
    return {
      version: 1,
      active: parsed.active === true,
      orgId: typeof parsed.orgId === "number" ? parsed.orgId : null,
      sessionId: typeof parsed.sessionId === "number" ? parsed.sessionId : null,
      currentModuleId:
        typeof parsed.currentModuleId === "string" ? parsed.currentModuleId : null,
      currentStepIndex:
        typeof parsed.currentStepIndex === "number" ? parsed.currentStepIndex : 0,
      modules: parsed.modules && typeof parsed.modules === "object" ? parsed.modules : {},
    };
  } catch {
    return emptyProgress();
  }
}

export function writeTutorialProgress(progress: TutorialProgress): void {
  localStorage.setItem(TUTORIAL_STORAGE_KEY, JSON.stringify(progress));
}

export function updateTutorialProgress(
  patch: Partial<TutorialProgress>,
): TutorialProgress {
  const next = { ...readTutorialProgress(), ...patch };
  writeTutorialProgress(next);
  return next;
}

export function setModuleStatus(moduleId: string, status: ModuleStatus): TutorialProgress {
  const progress = readTutorialProgress();
  progress.modules = {
    ...progress.modules,
    [moduleId]: {
      status,
      ...(status === "completed" ? { completedAt: new Date().toISOString() } : {}),
    },
  };
  writeTutorialProgress(progress);
  return progress;
}

export function clearTutorialProgress(): void {
  localStorage.removeItem(TUTORIAL_STORAGE_KEY);
}
