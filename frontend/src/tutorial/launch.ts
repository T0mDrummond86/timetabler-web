/** Dashboard entry point: find-or-create the sandbox and activate the tutorial. */
import { api } from "../api";
import { updateTutorialProgress } from "./progress";

/** Returns the URL to navigate to (the sandbox timetable). */
export async function launchTutorial(orgId: number): Promise<string> {
  const started = await api.startTutorial(orgId);
  updateTutorialProgress({
    active: true,
    orgId,
    sessionId: started.session.id,
    // Land on the module picker; a brand-new run has nothing in progress.
    currentModuleId: null,
    currentStepIndex: 0,
  });
  return `/timetable/${started.session.id}?tab=timetable`;
}
