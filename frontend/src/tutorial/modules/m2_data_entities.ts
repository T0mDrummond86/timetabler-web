/** Module 2 — Data & entities: staff, rooms, classes editors. */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

const SEEDED_STAFF = new Set([
  "Priya Sharma",
  "Tom Nguyen",
  "Marcus Webb",
  "David Chen",
  "James Taylor",
  "Elena Rodriguez",
  "Sarah O'Brien",
  "Aisha Khan",
]);

export const m2DataEntities: TutorialModule = {
  id: "m2_data_entities",
  title: "Data & entities",
  goal: "Meet the Staff, Rooms and Classes editors — and add a lecturer.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=staff`,
  steps: [
    {
      id: "open-staff",
      title: "Open the Staff tab",
      body:
        "Everything on a timetable hangs off data: lecturers, rooms, classes, qualifications. Start with the people — open the Staff tab.",
      advance: "verify",
      target: "tab-staff",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "staff",
    },
    {
      id: "add-staff",
      title: "Add a lecturer",
      body:
        "The table lists each lecturer with their FTE and weekly hours. An FTE of 1.0 means a 21-hour teaching load; the Variance column shows who's over or under.\n\nAdd a new staff member named after yourself — use the add-staff form on this tab (any FTE you like).",
      advance: "verify",
      target: "tab-staff",
      watch: { api: /\/staff/ },
      verify: async (ctx) => {
        const staff = await api.staff(ctx.sessionId);
        return staff.some((s) => !SEEDED_STAFF.has(s.name));
      },
      hint: "Scroll the Staff tab to its add-staff form, type your name, and save. The list should grow to nine.",
    },
    {
      id: "competencies",
      title: "Competencies = who may teach what",
      body:
        "Each class keeps an allowed-lecturers list (competencies). Assign someone outside the list and the timetable flags a warning rather than blocking you — you'll see one of those in the Clashes module.\n\nNotice Priya Sharma's variance: she's already over her part-time load. That's a job for the Staff hours module.",
      advance: "next",
    },
    {
      id: "open-rooms",
      title: "Open the Rooms tab",
      body:
        "Rooms carry a delivery type (on-campus / online) and a capacity. Open the Rooms tab and find A1.10 — a 12-seat seminar room. Remember it: someone has scheduled a 25-student First Aid class in there.",
      advance: "verify",
      target: "tab-rooms",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "rooms",
    },
    {
      id: "open-classes",
      title: "Open the Classes tab",
      body:
        "Classes are what gets scheduled. Each has a length, room requirements, and its study-unit codes — find Interactive Web Security, which bundles two codes (VU23218, VU23219). Some classes, like Cyber Incident Response, are double sessions: two bookings a week.",
      advance: "verify",
      target: "tab-units",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "units",
    },
  ],
  recap: [
    "Staff carry FTE → load; variance shows over/under-allocation.",
    "Rooms have a type and capacity; classes can demand both.",
    "Competency lists warn when the wrong lecturer is assigned.",
  ],
};
