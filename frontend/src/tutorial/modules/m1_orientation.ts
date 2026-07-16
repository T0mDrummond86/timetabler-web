/** Module 1 — Orientation: layout, tabs, views, holding area. */
import type { TutorialModule } from "../types";
import { urlIntParam, urlTab, urlView } from "../verifyHelpers";

export const m1Orientation: TutorialModule = {
  id: "m1_orientation",
  title: "Orientation",
  goal: "Find your way around: tabs, views, and the holding area.",
  startUrl: (ctx) =>
    `/timetable/${ctx.sessionId}?tab=timetable&view=course&course=${ctx.entities.courses["CYB-A"] ?? ""}`,
  steps: [
    {
      id: "welcome",
      title: "Welcome to the sandbox",
      body:
        "You're in a practice timetable for a fictional TAFE campus — real staff-room drama, zero real consequences. Everything you do here stays in this sandbox.\n\nThis panel guides you step by step and automatically notices when you've done each task. You can collapse it, skip steps, or leave and resume any time.",
      advance: "next",
    },
    {
      id: "tabs",
      title: "The session tabs",
      body:
        "Across the top are this timetable's work areas: Timetable is where you schedule; Warnings lists rule breaches; Staff, Rooms, Classes and Qualifications hold your data; Lecturer cover and Change log support day-to-day running.",
      advance: "next",
      target: "session-tabs",
    },
    {
      id: "open-warnings",
      title: "Open the Warnings tab",
      body:
        "Click the Warnings tab. This sandbox ships with some deliberate problems — you'll fix them in a later module.",
      advance: "verify",
      target: "tab-warnings",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "warnings",
      hint: "The Warnings tab is in the tab strip at the top — it shows a count badge.",
    },
    {
      id: "back-to-timetable",
      title: "Back to the Timetable tab",
      body: "Now return to the Timetable tab — that's where the scheduling happens.",
      advance: "verify",
      target: "tab-timetable",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "timetable",
    },
    {
      id: "staff-view",
      title: "Switch to a lecturer's week",
      body:
        "The sidebar's View selector changes what the grid shows. Switch the view to Staff, then pick Tom Nguyen from the list — you're looking at one lecturer's whole week.",
      advance: "verify",
      target: "sidebar",
      watch: { url: true },
      verify: (ctx) =>
        urlView(ctx) === "staff" &&
        urlIntParam(ctx, "staff") === ctx.entities.staff["Tom Nguyen"],
      hint: "Use the View dropdown in the left sidebar, choose Staff, then click Tom Nguyen in the list below it. (Spot anything odd about his Monday?)",
    },
    {
      id: "holding-area",
      title: "The holding area",
      body:
        "Switch back to thinking in courses: each course's unscheduled classes wait in the holding area below the grid. Dragging a class from there onto the grid schedules it — dragging a placed card back unschedules it.\n\nCYB-A has one class waiting. You'll place it in the Build module.",
      advance: "next",
      target: "holding-area",
    },
  ],
  recap: [
    "Tabs along the top switch between work areas.",
    "The sidebar picks the view: by course, lecturer, room, or day.",
    "Unscheduled classes wait in the holding area under the grid.",
  ],
};
