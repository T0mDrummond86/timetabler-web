/** Tutorial step engine: watches API events / URL changes, runs verifies, advances.
 *
 * Verification never inspects gestures — a step passes only when the backend
 * (or URL) state it teaches is actually in place, so out-of-order work and
 * already-done steps pass automatically.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { onApiEvent } from "./apiEvents";
import type { TutorialEntityMap, TutorialModule, TutorialStep, VerifyCtx } from "./types";

const FALLBACK_POLL_MS = 5000;
const HINT_OFFER_MS = 25000;
const PASS_FLASH_MS = 700;

export type StepPhase = "waiting" | "checking" | "passed";

export type EngineState = {
  step: TutorialStep | null;
  /** steps.length means "show the recap screen". */
  stepIndex: number;
  stepCount: number;
  phase: StepPhase;
  hintOffered: boolean;
};

export function useTutorialEngine(opts: {
  module: TutorialModule | null;
  stepIndex: number;
  sessionId: number;
  orgId: number;
  entities: TutorialEntityMap | null;
  onAdvance: (nextIndex: number) => void;
}) {
  const { module, stepIndex, sessionId, orgId, entities, onAdvance } = opts;
  const location = useLocation();
  const [phase, setPhase] = useState<StepPhase>("waiting");
  const [hintOffered, setHintOffered] = useState(false);

  const step: TutorialStep | null =
    module && stepIndex >= 0 && stepIndex < module.steps.length
      ? module.steps[stepIndex]
      : null;

  const ctx: VerifyCtx | null = useMemo(() => {
    if (!entities) return null;
    return {
      sessionId,
      orgId,
      entities,
      url: {
        pathname: location.pathname,
        params: new URLSearchParams(location.search),
      },
    };
  }, [entities, sessionId, orgId, location.pathname, location.search]);

  // Reset per-step state when the step changes.
  useEffect(() => {
    setPhase("waiting");
    setHintOffered(false);
  }, [module?.id, stepIndex]);

  const verifyBusy = useRef(false);
  const stepKey = `${module?.id ?? ""}:${stepIndex}`;
  const stepKeyRef = useRef(stepKey);
  stepKeyRef.current = stepKey;

  const runVerify = useCallback(async () => {
    if (!step || step.advance !== "verify" || !step.verify || !ctx) return;
    if (verifyBusy.current) return;
    verifyBusy.current = true;
    const keyAtStart = stepKeyRef.current;
    setPhase((p) => (p === "passed" ? p : "checking"));
    let ok = false;
    try {
      ok = await step.verify(ctx);
    } catch {
      ok = false;
    } finally {
      verifyBusy.current = false;
    }
    if (stepKeyRef.current !== keyAtStart) return; // step changed mid-check
    if (ok) {
      setPhase("passed");
      window.setTimeout(() => {
        if (stepKeyRef.current === keyAtStart) onAdvance(stepIndex + 1);
      }, PASS_FLASH_MS);
    } else {
      setPhase("waiting");
    }
  }, [step, ctx, stepIndex, onAdvance]);

  const runVerifyRef = useRef(runVerify);
  runVerifyRef.current = runVerify;

  // Trigger 1: matching API calls.
  useEffect(() => {
    if (!step || step.advance !== "verify") return;
    const pattern = step.watch?.api;
    if (!pattern) return;
    return onApiEvent((event) => {
      if (event.ok && pattern.test(event.path)) void runVerifyRef.current();
    });
  }, [step]);

  // Trigger 2: URL changes (tab/view navigation steps) + initial check.
  useEffect(() => {
    if (!step || step.advance !== "verify" || step.eventOnly) return;
    void runVerifyRef.current();
    // Location object in deps re-runs this on every URL change.
  }, [step, location.pathname, location.search]);

  // Trigger 3: slow fallback poll (covers undo, second-tab edits, misses).
  useEffect(() => {
    if (!step || step.advance !== "verify" || step.eventOnly) return;
    const id = window.setInterval(() => void runVerifyRef.current(), FALLBACK_POLL_MS);
    return () => window.clearInterval(id);
  }, [step]);

  // Offer the hint after idling on a verify step.
  useEffect(() => {
    if (!step || step.advance !== "verify" || !step.hint) return;
    const id = window.setTimeout(() => setHintOffered(true), HINT_OFFER_MS);
    return () => window.clearTimeout(id);
  }, [step]);

  const state: EngineState = {
    step,
    stepIndex,
    stepCount: module?.steps.length ?? 0,
    phase,
    hintOffered,
  };
  return state;
}
