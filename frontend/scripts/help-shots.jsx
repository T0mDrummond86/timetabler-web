/** Scenes for the help screenshots.
 *
 * These are the app's own components and the app's own stylesheet, rendered
 * with stand-in data, rather than captures of a running session. That trade was
 * deliberate: driving the live app needs an authenticated session, and the only
 * way to get one headlessly was to weaken auth on the dev stack.
 *
 * Where a component is prop-driven it is mounted for real (HoldingAreaPanel,
 * DataToolbar), so those shots are the genuine article. Where a component
 * fetches its own data, the markup is reproduced using the same class names and
 * the same wording as the app, checked against the source. Either way the CSS is
 * the real stylesheet, so the result matches what a user sees.
 *
 * The fixture names are invented and obviously so — no real lecturer appears in
 * a help screenshot.
 */
import React from "react";
import { createRoot } from "react-dom/client";
import "../src/index.css";
import { HoldingAreaPanel } from "../src/components/HoldingAreaPanel";
import { DataToolbar } from "../src/components/DataToolbar";
import { StaffHoursTable } from "../src/components/StaffHoursTable";
import { StaffAvailabilityGrid } from "../src/components/StaffAvailabilityGrid";
import { ClassCustodiansTable } from "../src/components/ClassCustodiansTable";
import { ChangeLogPanel } from "../src/components/ChangeLogPanel";
import { ViolationsReportPanel } from "../src/components/ViolationsReportPanel";
import { ClashSettingsPanel } from "../src/components/ClashSettingsPanel";
import { StageSplitDialog } from "../src/components/StageSplitDialog";
import { QualificationMergeDialog } from "../src/components/QualificationMergeDialog";

/* ------------------------------------------------------------- fetch stub */

/** Canned responses, so components that load their own data can be mounted.
 *
 * Matched on the path only, ignoring query strings, because most of these
 * endpoints carry filters the screenshot does not care about. Anything
 * unmatched rejects loudly rather than hanging: a scene quietly showing its
 * loading state would be captured as a picture of the word "Loading".
 */
const STUB = [
  [/\/change-log/, () => ({
    mode: "resolved",
    rows: [
      {
        when: "2026-03-02T09:15:00Z", action: "net", booking_id: 11, entry_id: 1, note: "",
        lecturers: ["A. Rivers"],
        current: { lecturer: "A. Rivers", time: "09:00–11:00", day: "Mon", room: "B2.14" },
        row: {
          id: "C-114", group: "Cert IV Cyber GrpA",
          class: "Design and implement a server solution",
          day_change: "Tue → Mon", time_change: "13:00 → 09:00",
        },
      },
      {
        when: "2026-03-02T10:02:00Z", action: "net", booking_id: 12, entry_id: 2, note: "swapped at short notice",
        lecturers: ["B. Nakamura", "C. Okonkwo"],
        current: { lecturer: "C. Okonkwo", time: "11:00–13:00", day: "Wed", room: "B2.09" },
        row: {
          id: "C-118", group: "Cert IV Cyber GrpB",
          class: "Gather and interpret threat data",
          lecturer_change: "B. Nakamura → C. Okonkwo",
        },
      },
    ],
  })],
  [/\/violations-report/, () => ({
    summary: "2 hard, 1 soft",
    headers: ["severity", "rule", "class", "group", "lecturer", "room", "when"],
    rows: [
      { severity: "hard", rule: "Room double-booking", class: "Design and implement a server solution",
        group: "Cert IV Cyber GrpA", lecturer: "A. Rivers", room: "B2.14", when: "Mon 09:00" },
      { severity: "hard", rule: "Staff double-booking", class: "Gather and interpret threat data",
        group: "Cert IV Cyber GrpB", lecturer: "A. Rivers", room: "B2.09", when: "Mon 09:00" },
      { severity: "soft", rule: "Lecturer not on allowed list", class: "Manage client problems",
        group: "Cert IV Cyber GrpA", lecturer: "C. Okonkwo", room: "A1.02", when: "Thu 14:00" },
    ],
  })],
  [/\/clash-settings/, () => [
    { code: "room_double_booking", label: "Room double-booking", severity: "hard", category: "clashes",
      description: "Same physical room booked twice at overlapping times.", enabled: true },
    { code: "staff_double_booking", label: "Staff double-booking", severity: "hard", category: "clashes",
      description: "Same lecturer assigned to overlapping classes.", enabled: true },
    { code: "course_clash", label: "Course class overlap", severity: "hard", category: "clashes",
      description: "Two classes for the same course cohort overlap in time.", enabled: true },
    { code: "room_capacity", label: "Room too small", severity: "hard", category: "rooms",
      description: "Room capacity is below the class required capacity.", enabled: true },
    { code: "room_type", label: "Wrong room type", severity: "hard", category: "rooms",
      description: "Room type does not match the class requirement.", enabled: false },
  ]],
  [/\/stage-split/, () => ({
    qualification_id: 1, name: "Cert IV Cyber Security", num_groups: 2,
    can_split: true, blocked_reason: "",
    classes: [
      { id: 1, name: "Design and implement a server solution" },
      { id: 2, name: "Gather and interpret threat data" },
      { id: 3, name: "Manage client problems" },
      { id: 4, name: "Originate and develop concepts" },
    ],
  })],
  [/\/qualifications\/merge-preview/, () => ({
    first: { id: 1, name: "Cert IV Cyber Stg1", num_groups: 2, schedule_period: "day",
      delivery_mode: "regular", class_count: 4, booking_count: 6 },
    second: { id: 2, name: "Cert IV Cyber Stg2", num_groups: 1, schedule_period: "day",
      delivery_mode: "regular", class_count: 3, booking_count: 2 },
    shared_class_count: 1, combined_class_count: 6,
    combined_classes: [
      { id: 1, name: "Design and implement a server solution" },
      { id: 2, name: "Gather and interpret threat data" },
      { id: 3, name: "Manage client problems" },
    ],
    suggested_name: "Cert IV Cyber Stg1 + Cert IV Cyber Stg2",
    suggested_num_groups: 2,
    warnings: ["1 class(es) already belong to both, and are counted once."],
  })],
];

const realFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url;
  const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
  for (const [re, body] of STUB) {
    if (re.test(path)) {
      return new Response(JSON.stringify(body()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
  }
  // Only the app's own API is stubbed; module and asset loads must pass through.
  if (/^\/(sessions|orgs|global-sessions|auth)\//.test(path)) {
    throw new Error(`help-shots: no stub for ${path}`);
  }
  return realFetch(input, init);
};

/* ---------------------------------------------------------------- fixtures */

const HOLDING = [
  { unit_id: 1, unit_name: "Design and implement a server solution", duration_slots: 4, session_part: 1 },
  { unit_id: 2, unit_name: "Originate and develop concepts", duration_slots: 4, session_part: 1 },
  { unit_id: 3, unit_name: "Gather and interpret threat data", duration_slots: 6, session_part: 1 },
  { unit_id: 4, unit_name: "Manage client problems", duration_slots: 2, session_part: 1 },
];

function hoursRow(id, name, fte, inClass, variance, category) {
  return {
    id, name, cost_centre: "IT", fte,
    lecturing_hours: fte * 21,
    in_class_timetabled_hours: inClass,
    session_schedule_avg: null,
    variance, variance_category: category,
    bulk_online_detail: null, bulk_online_hours_avg: 0,
    development_project_hours: 0, development_project_description: null,
    tae_hours: 0, supervision_hours: 0,
    total_hours: fte * 21 + variance,
    non_teaching_day: null,
    preferences_first: "", preferences_second: "", preferences_third: "",
  };
}

const HOURS = [
  hoursRow(1, "A. Rivers", 1, 18, 3.5, "overtime"),
  hoursRow(2, "B. Nakamura", 1, 15, -2, "shortfall"),
  hoursRow(3, "C. Okonkwo", 0.5, 9, 0, "balanced"),
];

const CUSTODIANS = [
  {
    unit_id: 1, unit_name: "Design and implement a server solution",
    qualifications: "Cert IV Cyber Security", lecturers: "A. Rivers, B. Nakamura",
    custodian: "A. Rivers", custodian_staff_id: 1, custodian_deliveries: 4,
    custodian_is_manual: false,
    candidates: [
      { staff_id: 1, name: "A. Rivers", deliveries: 4 },
      { staff_id: 2, name: "B. Nakamura", deliveries: 1 },
    ],
  },
  {
    unit_id: 2, unit_name: "Gather and interpret threat data",
    qualifications: "Cert IV Cyber Security", lecturers: "C. Okonkwo",
    custodian: "C. Okonkwo", custodian_staff_id: 3, custodian_deliveries: 2,
    custodian_is_manual: true,
    candidates: [{ staff_id: 3, name: "C. Okonkwo", deliveries: 2 }],
  },
];

/** A few blocked slots, so the grid shows both states. */
const BLOCKED = new Set(["0:0", "0:1", "0:2", "0:3", "2:16", "2:17", "2:18", "4:20", "4:21"]);

/* ------------------------------------------------------------------ scenes */

function Placecard({ variant }) {
  const tone =
    variant === "hard" ? "#cfe3f5" : variant === "soft" ? "#f0e0c8" : "#cfe3f5";
  const cls =
    "booking-card" +
    (variant === "hard" ? " violation-hard" : variant === "soft" ? " violation-soft" : "");
  return (
    <div className="scene" style={{ background: "var(--grid-body-bg)" }}>
      <div style={{ position: "relative", width: 240, height: 96 }}>
        <div className={cls} style={{ inset: 0, background: tone, position: "absolute" }}>
          {/* The badge sits in the time row in WeekGridView, not the title. */}
          <div className="booking-card-time">
            09:00–11:00
            {variant === "locked" && <span className="booking-lock-badge">🔒</span>}
          </div>
          <div className="booking-card-title">Design and implement a server solution</div>
          <div className="booking-card-meta">A. Rivers</div>
          <div className="booking-card-room">Room B2.14</div>
        </div>
      </div>
    </div>
  );
}

function Toolbar({ open }) {
  // The real component. Its menus are static markup, so opening one is just a
  // click -- no session, no network.
  return (
    <div className="scene" style={{ background: "var(--zone-toolbar)", minHeight: 460 }}>
      <div className="tt-toolbar" style={{ display: "flex", gap: "0.4rem" }}>
        <DataToolbar
          sessionId={1}
          colourByClass={false}
          onColourByClassChange={() => {}}
          showAlerts
          onShowAlertsChange={() => {}}
          autoClashDetect
          onAutoClashDetectChange={() => {}}
          onCheckClashes={() => {}}
          onImport={() => {}}
          zoomPercent={100}
          onZoomIn={() => {}}
          onZoomOut={() => {}}
          onZoomReset={() => {}}
        />
      </div>
      <span data-open-menu={open} hidden />
    </div>
  );
}

function Holding() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 360 }}>
      <HoldingAreaPanel items={HOLDING} />
    </div>
  );
}

function CoverToolbar() {
  return (
    <div className="scene" style={{ background: "var(--zone-toolbar)" }}>
      <div className="lecturer-cover-toolbar">
        <div className="lecturer-cover-toolbar-group">
          <span className="lecturer-cover-toolbar-label">Lecturer requiring cover</span>
          <select className="field-select lecturer-cover-select" defaultValue="1">
            <option value="1">A. Rivers</option>
          </select>
        </div>
        <div className="lecturer-cover-toolbar-group">
          <label className="lecturer-cover-toolbar-label" htmlFor="wk">Week beginning</label>
          <input id="wk" type="date" className="field-input cover-request-date" defaultValue="2026-03-02" />
        </div>
      </div>
    </div>
  );
}

function ClashSettings() {
  const rows = [
    ["Room double-booking", "Same physical room booked twice at overlapping times."],
    ["Staff double-booking", "Same lecturer assigned to overlapping classes."],
    ["Course class overlap", "Two classes for the same course cohort overlap in time."],
  ];
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 360 }}>
      <div className="clash-settings-group">
        <h3>Double-booking &amp; clashes</h3>
        {rows.map(([label, desc]) => (
          <div key={label}>
            <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <input type="checkbox" defaultChecked />
              <span>{label}</span>
            </label>
            <p className="clash-settings-desc muted">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Normal card beside a clashing one.
 *
 * No annotation ring on this scene: the red border is itself the thing being
 * explained, and a red ring around a red border reads as one thick smear. The
 * contrast with a normal card is what makes the point. */
function PlacecardPair() {
  const card = (variant) => (
    <div style={{ position: "relative", width: 230, height: 96 }}>
      <div
        className={"booking-card" + (variant ? ` violation-${variant}` : "")}
        style={{ inset: 0, background: "#cfe3f5", position: "absolute" }}
      >
        <div className="booking-card-time">09:00–11:00</div>
        <div className="booking-card-title">Design and implement a server solution</div>
        <div className="booking-card-meta">A. Rivers</div>
      </div>
    </div>
  );
  return (
    <div
      className="scene"
      // Stacked, not side by side: two 230px cards in a row is wider than the
      // help panel, and the comparison reads just as well vertically.
      style={{
        background: "var(--grid-body-bg)",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        width: 230 + 56, // card width + the scene's own padding (border-box)
      }}
    >
      {card(null)}
      {card("hard")}
    </div>
  );
}

function Hours() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 470 }}>
      <StaffHoursTable rows={HOURS} selectedId={1} onSelect={() => {}} />
    </div>
  );
}

function Availability() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 420 }}>
      <StaffAvailabilityGrid blocked={BLOCKED} onChange={() => {}} />
    </div>
  );
}

function Custodians() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 560 }}>
      <ClassCustodiansTable
        rows={CUSTODIANS}
        allStaff={[
          { id: 1, name: "A. Rivers" },
          { id: 2, name: "B. Nakamura" },
          { id: 3, name: "C. Okonkwo" },
        ]}
        onReassign={() => {}}
      />
    </div>
  );
}

function ChangeLog() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 430 }}>
      <ChangeLogPanel sessionId={1} />
    </div>
  );
}

function Warnings() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 420 }}>
      <ViolationsReportPanel sessionId={1} />
    </div>
  );
}

function RealClashSettings() {
  return (
    <div className="scene" style={{ background: "var(--zone-main)", width: 470 }}>
      <ClashSettingsPanel sessionId={1} />
    </div>
  );
}

function StageSplit() {
  return <StageSplitDialog sessionId={1} qualificationId={1} onClose={() => {}} onSplit={() => {}} />;
}

function Merge() {
  return (
    <QualificationMergeDialog
      sessionId={1}
      qualificationId={1}
      qualifications={[
        { id: 1, name: "Cert IV Cyber Stg1", num_groups: 2, schedule_period: "day" },
        { id: 2, name: "Cert IV Cyber Stg2", num_groups: 1, schedule_period: "day" },
      ]}
      onClose={() => {}}
      onMerge={() => {}}
    />
  );
}

const SCENES = {
  placecard: <Placecard variant="plain" />,
  "placecard-locked": <Placecard variant="locked" />,
  "placecard-warning": <PlacecardPair />,
  "toolbar-import": <Toolbar open="import" />,
  "toolbar-export": <Toolbar open="export" />,
  holding: <Holding />,
  "cover-toolbar": <CoverToolbar />,
  "clash-settings": <ClashSettings />,
  "toolbar-display": <Toolbar open="display" />,
  hours: <Hours />,
  availability: <Availability />,
  custodians: <Custodians />,
  changelog: <ChangeLog />,
  warnings: <Warnings />,
  "clash-settings-real": <RealClashSettings />,
  "stage-split": <StageSplit />,
  merge: <Merge />,
};

const scene = new URLSearchParams(location.search).get("scene") || "placecard";
createRoot(document.getElementById("root")).render(
  SCENES[scene] ?? <p style={{ color: "red", padding: 20 }}>Unknown scene: {scene}</p>,
);
