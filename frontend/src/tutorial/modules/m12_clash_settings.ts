/** Module 12 — tuning clash detection.
 *
 * Two different dials that are easy to confuse: which checks run at all
 * (Clash settings, per session) and whether the grid re-checks as you drag
 * (Display ▾ → auto clash detection, per browser). The module has the learner
 * turn each off and back on, watching what changes.
 */
import { api } from "../../api";
import { readDisplayPrefs } from "../../lib/displayPrefs";
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

async function roomCapacityEnabled(sessionId: number): Promise<boolean | null> {
  const settings = await api.clashSettings(sessionId);
  const row = settings.find((s) => s.code === "room_capacity");
  return row ? row.enabled : null;
}

export const m12ClashSettings: TutorialModule = {
  id: "m12_clash_settings",
  title: "Tuning clash detection",
  section: "Tutorial 2 — Running the timetable",
  goal: "Choose which checks run, and when the grid re-checks.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=clash_settings`,
  steps: [
    {
      id: "open-clash-settings",
      title: "Open Clash settings",
      body:
        "Not every rule matters to every campus, so the checks themselves are configurable per session. Open the Clash settings tab: each check has a description, a hard/soft severity, and an on/off toggle.\n\nA few of the noisier soft checks are already off in this sandbox — that's this screen doing its job.",
      advance: "verify",
      target: "tab-clash_settings",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "clash_settings",
    },
    {
      id: "disable-room-capacity",
      title: "Turn a check off",
      body:
        "First Aid Essentials meets in A1.10, a 12-seat seminar room, with 12 enrolled — the Warnings tab carries a room-capacity warning for it.\n\nFind \"Room too small\" here and switch it off, then look at the Warnings tab: the warning is gone. Not fixed — gone. Disabling a check silences it everywhere, which is exactly why this screen deserves respect.",
      advance: "verify",
      watch: { api: /\/clash-settings/ },
      verify: async (ctx) => (await roomCapacityEnabled(ctx.sessionId)) === false,
      hint: "Clash settings tab → find Room too small → toggle it off. The change saves immediately.",
    },
    {
      id: "reenable-room-capacity",
      title: "Turn it back on",
      body:
        "Switch Room too small back on. The warning returns — the overcrowded room never stopped being overcrowded, the app just stopped mentioning it.\n\nRule of thumb: disable a check because it doesn't apply to how you timetable, never because a particular warning is annoying you today.",
      advance: "verify",
      watch: { api: /\/clash-settings/ },
      verify: async (ctx) => (await roomCapacityEnabled(ctx.sessionId)) === true,
      hint: "Same toggle, back on. Reset to defaults is there too if a session's settings get into a state.",
    },
    {
      id: "clash-view-off",
      title: "The other dial: auto clash detection",
      body:
        "Separate from which checks exist is when they run. On the Timetable tab, open Display ▾ and untick \"Auto clash detection\".\n\nThe grid stops re-checking after every drag — on a big timetable that makes rearranging noticeably snappier — and a \"Check clashes\" button appears in the toolbar so you can run the checks when you choose.",
      advance: "verify",
      verify: () => !readDisplayPrefs().autoClashDetect,
      hint: "Timetable tab → Display ▾ → untick Auto clash detection. This one is a display preference — it's per browser, not per session.",
    },
    {
      id: "clash-view-on",
      title: "And back on",
      body:
        "Tick it back on. For a sandbox this size there's no reason to leave it off — the manual button earns its keep on timetables with hundreds of classes.",
      advance: "verify",
      verify: () => readDisplayPrefs().autoClashDetect,
    },
  ],
  recap: [
    "Clash settings decide which checks run — per session, saved for everyone.",
    "Disabling a check silences the warning without fixing the problem.",
    "Display ▾ → Auto clash detection decides when checks run — per browser, with a manual Check clashes button when off.",
  ],
};
