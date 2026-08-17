/** Docked tutorial panel + module picker + highlight ring.
 *
 * Renders through a portal so TimetablePage layout is untouched; self-hides
 * unless the tutorial is active for this exact session. All interaction with
 * the app happens through the user's own clicks — the panel only watches.
 */
import { Fragment, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { onApiEvent } from "./apiEvents";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";
import { useDropdown } from "../hooks/useDropdown";
import { LoadingMark } from "../components/LoadingMark";
import { HighlightRing } from "./HighlightRing";
import { useTutorialEngine } from "./engine";
import { TUTORIAL_MODULES } from "./modules";
import {
  clearTutorialProgress,
  readTutorialProgress,
  setModuleStatus,
  updateTutorialProgress,
} from "./progress";
import type { TutorialEntityMap, TutorialModule, TutorialProgress } from "./types";

const STATUS_LABEL: Record<string, string> = {
  completed: "Done",
  skipped: "Skipped",
  in_progress: "In progress",
};

export function TutorialHost({ sessionId }: { sessionId: number }) {
  const navigate = useNavigate();
  const { confirm, dialogs } = useConfirmPrompt();
  const menu = useDropdown();
  const [progress, setProgress] = useState<TutorialProgress>(readTutorialProgress);
  const [entities, setEntities] = useState<TutorialEntityMap | null>(null);
  const orgId = progress.orgId ?? 0;
  const [collapsed, setCollapsed] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const active = progress.active && progress.sessionId === sessionId;

  // The panel is fixed, so the app has to give up the width itself or the
  // panel just covers it. Cleared on unmount too, or leaving the tutorial
  // would strand the gutter with nothing in it.
  useEffect(() => {
    const docked = active && !collapsed;
    document.body.classList.toggle("tutorial-docked", docked);
    return () => document.body.classList.remove("tutorial-docked");
  }, [active, collapsed]);

  const apply = useCallback((patch: Partial<TutorialProgress>) => {
    setProgress(updateTutorialProgress(patch));
  }, []);

  // Confirm this really is the caller's sandbox and load the entity map.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void (async () => {
      try {
        const info = await api.tutorialInfo(sessionId);
        if (cancelled) return;
        if (!info.is_tutorial) {
          setProgress(updateTutorialProgress({ active: false }));
          return;
        }
        setEntities(info.entities as TutorialEntityMap);
      } catch {
        if (!cancelled) setEntities(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, sessionId]);

  // Imports can replace entity rows wholesale (a session restore certainly
  // does), which strands every cached id. Refetch the map when one lands.
  useEffect(() => {
    if (!active) return;
    return onApiEvent((event) => {
      if (!event.ok || !/\/import(\/|$)/.test(event.path)) return;
      void api
        .tutorialInfo(sessionId)
        .then((info) => {
          if (info.is_tutorial) setEntities(info.entities as TutorialEntityMap);
        })
        .catch(() => {
          /* the next module start refetches anyway */
        });
    });
  }, [active, sessionId]);

  const currentModule: TutorialModule | null =
    TUTORIAL_MODULES.find((m) => m.id === progress.currentModuleId) ?? null;

  const onAdvance = useCallback(
    (nextIndex: number) => {
      setShowHint(false);
      apply({ currentStepIndex: nextIndex });
    },
    [apply],
  );

  const engine = useTutorialEngine({
    module: currentModule,
    stepIndex: progress.currentStepIndex,
    sessionId,
    orgId,
    entities,
  });

  if (!active) return null;

  function startModule(mod: TutorialModule) {
    setShowHint(false);
    setModuleStatus(mod.id, "in_progress");
    apply({ currentModuleId: mod.id, currentStepIndex: 0 });
    // Deliberately no navigate(mod.startUrl): TimetablePage only parses URL
    // params on mount, so a same-route navigation would change the URL without
    // changing the visible view — making nav-step verifies pass untruthfully.
    // Each module's first step walks the user to the right place instead.
  }

  function backToPicker() {
    setShowHint(false);
    apply({ currentModuleId: null });
  }

  function finishModule(mod: TutorialModule) {
    setProgress(setModuleStatus(mod.id, "completed"));
    apply({ currentModuleId: null, currentStepIndex: 0 });
  }

  function skipModule(mod: TutorialModule) {
    setProgress(setModuleStatus(mod.id, "skipped"));
    apply({ currentModuleId: null, currentStepIndex: 0 });
  }

  async function resetSandbox() {
    menu.close();
    const ok = await confirm({
      title: "Reset sandbox data",
      message:
        "This erases every change in the tutorial sandbox and restores the original sample data. Your real timetables are not touched.",
      confirmLabel: "Reset sandbox",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const result = await api.resetTutorial(sessionId);
      // Restore re-creates every row with fresh ids — refresh the entity map
      // or step verifies would compare against stale ids.
      setEntities(result.entities as TutorialEntityMap);
      setNotice("Sandbox restored to its original state.");
      window.setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  function exitKeep() {
    menu.close();
    apply({ active: false });
  }

  async function exitDelete() {
    menu.close();
    const ok = await confirm({
      title: "Exit and delete sandbox",
      message:
        "This deletes the tutorial sandbox session entirely. You can restart the tutorial later — a fresh sandbox will be created.",
      confirmLabel: "Delete sandbox",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.deleteSession(sessionId);
      clearTutorialProgress();
      navigate("/dashboard");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Delete failed");
      setBusy(false);
    }
  }

  const completedCount = TUTORIAL_MODULES.filter(
    (m) => progress.modules[m.id]?.status === "completed",
  ).length;

  const panel = collapsed ? (
    <button
      type="button"
      className="tutorial-pill"
      onClick={() => setCollapsed(false)}
      aria-label="Reopen tutorial panel"
    >
      🎓 Tutorial · {completedCount}/{TUTORIAL_MODULES.length}
    </button>
  ) : (
    <aside className="tutorial-panel" aria-label="Tutorial">
      <header className="tutorial-panel-head">
        <span className="tutorial-panel-title">
          {currentModule ? currentModule.title : "Tutorial"}
        </span>
        <span className="tt-dropdown-wrap" ref={menu.wrapRef}>
          <button
            type="button"
            className="icon-btn"
            aria-haspopup="menu"
            aria-expanded={menu.open}
            aria-label="Tutorial options"
            onClick={menu.toggle}
          >
            ⋯
          </button>
          {menu.open && (
            <div className="tt-dropdown-menu tutorial-menu" role="menu">
              <button type="button" className="ctx-item" role="menuitem" onClick={() => void resetSandbox()}>
                Reset sandbox data…
              </button>
              <div className="ctx-divider" />
              <button type="button" className="ctx-item" role="menuitem" onClick={exitKeep}>
                Exit — keep sandbox
              </button>
              <button
                type="button"
                className="ctx-item ctx-item-danger"
                role="menuitem"
                onClick={() => void exitDelete()}
              >
                Exit &amp; delete sandbox…
              </button>
            </div>
          )}
        </span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse tutorial panel"
        >
          —
        </button>
      </header>

      {notice && <p className="tutorial-notice">{notice}</p>}
      {busy && <LoadingMark size={40} label="Working…" className="tutorial-busy" />}

      {!busy && !currentModule && (
        <div className="tutorial-picker">
          <p className="tutorial-goal">
            Learn TAFEtabler hands-on in a safe sandbox — your real timetables are never touched.
          </p>
          <div className="tutorial-progressbar" role="progressbar" aria-valuenow={completedCount} aria-valuemax={TUTORIAL_MODULES.length}>
            <div
              className="tutorial-progressbar-fill"
              style={{ width: `${(completedCount / TUTORIAL_MODULES.length) * 100}%` }}
            />
          </div>
          <ol className="tutorial-module-list">
            {TUTORIAL_MODULES.map((mod, i) => {
              const status = progress.modules[mod.id]?.status ?? "not_started";
              // A heading opens each tutorial; numbering restarts under it.
              const newSection = i === 0 || TUTORIAL_MODULES[i - 1].section !== mod.section;
              const numberInSection =
                i - TUTORIAL_MODULES.findIndex((m) => m.section === mod.section) + 1;
              return (
                <Fragment key={mod.id}>
                  {newSection && (
                    <li className="tutorial-section-heading" aria-hidden>
                      {mod.section}
                    </li>
                  )}
                  <li className="tutorial-module-row">
                  <div className="tutorial-module-info">
                    <span className="tutorial-module-name">
                      {numberInSection}. {mod.title}
                      {status !== "not_started" && (
                        <span className={`tutorial-chip tutorial-chip-${status}`}>
                          {STATUS_LABEL[status]}
                        </span>
                      )}
                    </span>
                    <span className="tutorial-module-goal muted">{mod.goal}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-secondary btn-xs"
                    disabled={!entities}
                    onClick={() => startModule(mod)}
                  >
                    {status === "completed" || status === "skipped"
                      ? "Replay"
                      : status === "in_progress"
                        ? "Resume"
                        : "Start"}
                  </button>
                  </li>
                </Fragment>
              );
            })}
          </ol>
        </div>
      )}

      {!busy && currentModule && engine.stepIndex >= currentModule.steps.length && (
        <div className="tutorial-step">
          <h3 className="tutorial-step-title">Module complete 🎉</h3>
          <ul className="tutorial-recap">
            {currentModule.recap.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <div className="tutorial-actions">
            <button type="button" className="btn-primary" onClick={() => finishModule(currentModule)}>
              Finish module
            </button>
          </div>
        </div>
      )}

      {!busy && currentModule && engine.step && (
        <div className="tutorial-step">
          <div className="tutorial-step-dots" aria-label={`Step ${engine.stepIndex + 1} of ${engine.stepCount}`}>
            {currentModule.steps.map((s, i) => (
              <span
                key={s.id}
                className={`tutorial-dot${i === engine.stepIndex ? " tutorial-dot-current" : i < engine.stepIndex ? " tutorial-dot-done" : ""}`}
              />
            ))}
          </div>
          <h3 className="tutorial-step-title">{engine.step.title}</h3>
          {engine.step.body.split("\n\n").map((para) => (
            <p key={para.slice(0, 40)} className="tutorial-step-body">
              {para}
            </p>
          ))}

          {engine.step.advance === "verify" && (
            <p className={`tutorial-verify tutorial-verify-${engine.phase}`} aria-live="polite">
              {engine.phase === "passed"
                ? "✓ Done! Read on, then press Next when you're ready."
                : engine.phase === "checking"
                  ? "Checking…"
                  : "Waiting for you — have a go."}
            </p>
          )}

          {showHint && engine.step.hint && (
            <p className="tutorial-hint">{engine.step.hint}</p>
          )}

          {engine.step.download && progress.sessionId != null && (
            <button
              type="button"
              className="btn-secondary btn-xs tutorial-download"
              onClick={() =>
                void api
                  .downloadExport(
                    `/sessions/${progress.sessionId}/tutorial-files/${engine.step!.download!.kind}`,
                    engine.step!.download!.filename,
                  )
                  .catch(() => setNotice("Download failed — is the API reachable?"))
              }
            >
              ⬇ {engine.step.download.label}
            </button>
          )}

          <div className="tutorial-actions">
            <button
              type="button"
              className="btn-primary btn-xs"
              disabled={engine.step.advance === "verify" && engine.phase !== "passed"}
              title={
                engine.step.advance === "verify" && engine.phase !== "passed"
                  ? "Have a go at this step first"
                  : undefined
              }
              onClick={() => onAdvance(engine.stepIndex + 1)}
            >
              Next
            </button>
            {engine.step.hint && !showHint && (
              <button
                type="button"
                className={`btn-secondary btn-xs${engine.hintOffered ? " tutorial-hint-offered" : ""}`}
                onClick={() => setShowHint(true)}
              >
                Hint
              </button>
            )}
            {engine.stepIndex > 0 && (
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => onAdvance(engine.stepIndex - 1)}
              >
                Back
              </button>
            )}
            {engine.step.advance === "verify" && (
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => onAdvance(engine.stepIndex + 1)}
              >
                Skip step
              </button>
            )}
          </div>
          <div className="tutorial-footer-links">
            <button type="button" className="tutorial-link" onClick={backToPicker}>
              All modules
            </button>
            <button
              type="button"
              className="tutorial-link"
              onClick={() => skipModule(currentModule)}
            >
              Skip module
            </button>
          </div>
        </div>
      )}
    </aside>
  );

  return createPortal(
    <>
      {panel}
      {!collapsed && <HighlightRing target={engine.step?.target} />}
      {dialogs}
    </>,
    document.body,
  );
}
