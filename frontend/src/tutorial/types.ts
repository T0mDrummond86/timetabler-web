/** Tutorial engine types: modules, steps, verification context. */

/** Name/code → id maps for the sandbox entities (from tutorial-info). */
export type TutorialEntityMap = {
  courses: Record<string, number>;
  units: Record<string, number>;
  staff: Record<string, number>;
  rooms: Record<string, number>;
  qualifications: Record<string, number>;
};

export type VerifyCtx = {
  sessionId: number;
  orgId: number;
  entities: TutorialEntityMap;
  url: { pathname: string; params: URLSearchParams };
};

export type TutorialStep = {
  id: string;
  title: string;
  /** Instruction body. Plain text; newlines become paragraphs. */
  body: string;
  /** data-tutorial-id of the element to ring-highlight (best effort). */
  target?: string;
  /** "verify" steps auto-advance when verify() passes; "next" steps show a Next button. */
  advance: "verify" | "next";
  /** What re-triggers verify: API calls matching a pattern and/or URL changes. */
  watch?: { api?: RegExp; url?: boolean };
  /** Verify ONLY on matching api events (no initial check / poll) — for actions
   *  with no queryable state, e.g. exports, where verify() returns true. */
  eventOnly?: boolean;
  verify?: (ctx: VerifyCtx) => Promise<boolean> | boolean;
  /** Shown via the Hint button (and auto-offered after idling on a verify step). */
  hint?: string;
};

export type TutorialModule = {
  id: string;
  title: string;
  goal: string;
  /** Where the module starts — navigated to on start/replay. */
  startUrl?: (ctx: VerifyCtx) => string;
  steps: TutorialStep[];
  recap: string[];
};

export type ModuleStatus = "not_started" | "in_progress" | "completed" | "skipped";

export type TutorialProgress = {
  version: 1;
  active: boolean;
  orgId: number | null;
  sessionId: number | null;
  currentModuleId: string | null;
  currentStepIndex: number;
  modules: Record<string, { status: ModuleStatus; completedAt?: string }>;
};
