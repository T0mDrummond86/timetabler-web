/** Module 7 — Capstone: schedule the CYB-T group clash-free, minimal hand-holding. */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { holdingUnitNames, urlIntParam, urlTab, urlView } from "../verifyHelpers";

export const m7Capstone: TutorialModule = {
  id: "m7_capstone",
  title: "Capstone",
  goal: "Schedule everything for the CYB-T group — clash-free, on your own.",
  startUrl: (ctx) =>
    `/timetable/${ctx.sessionId}?tab=timetable&view=course&course=${ctx.entities.courses["CYB-T"] ?? ""}`,
  steps: [
    {
      id: "brief",
      title: "Your mission",
      body:
        "The CYB-T capstone group still has four sessions in its holding area: Network Security Fundamentals, Workplace Communication, and both parts of the double-session Cyber Incident Response.\n\nSchedule all of them without creating a single hard warning. Everything you've learned applies: watch the cohort's existing classes, pick allowed lecturers and suitable rooms, and keep an eye on the Warnings tab.",
      advance: "next",
    },
    {
      id: "goto-cyb-t",
      title: "Open CYB-T",
      body: "Courses view → CYB-T. Its holding area shows the four waiting chips.",
      advance: "verify",
      target: "sidebar",
      watch: { url: true },
      verify: (ctx) =>
        urlTab(ctx) === "timetable" &&
        urlView(ctx) === "course" &&
        urlIntParam(ctx, "course") === ctx.entities.courses["CYB-T"],
    },
    {
      id: "schedule-all",
      title: "Schedule all four — clash-free",
      body:
        "Place every chip, assign lecturers and rooms as needed, and clear any hard warnings you create. This step completes when CYB-T's holding area is empty and no hard warning involves a CYB-T class.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const pending = await holdingUnitNames(ctx, "CYB-T");
        if (pending.length > 0) return false;
        const report = await api.violationsReport(ctx.sessionId, "hard");
        return !report.rows.some((row) => (row.group ?? "").includes("CYB-T"));
      },
      hint: "Free CYB-T slots: Monday & Thursday afternoons, most of Tuesday/Thursday. Tom, Priya and James cover the cyber classes; Elena or James can take Workplace Communication. Check each room's column before dropping — or right-click → Alternate slots and let the app choose.",
    },
  ],
  recap: [
    "You built a clash-free schedule unaided — holding area to finished timetable. 🎓",
    "That's the whole loop: data in, drag to schedule, watch the warnings, export out.",
    "Reset or delete this sandbox from the ⋯ menu whenever you like.",
  ],
};
