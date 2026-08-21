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

/* ---------------------------------------------------------------- fixtures */

const HOLDING = [
  { unit_id: 1, unit_name: "Design and implement a server solution", duration_slots: 4, session_part: 1 },
  { unit_id: 2, unit_name: "Originate and develop concepts", duration_slots: 4, session_part: 1 },
  { unit_id: 3, unit_name: "Gather and interpret threat data", duration_slots: 6, session_part: 1 },
  { unit_id: 4, unit_name: "Manage client problems", duration_slots: 2, session_part: 1 },
];

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

const SCENES = {
  placecard: <Placecard variant="plain" />,
  "placecard-locked": <Placecard variant="locked" />,
  "placecard-warning": <PlacecardPair />,
  "toolbar-import": <Toolbar open="import" />,
  "toolbar-export": <Toolbar open="export" />,
  holding: <Holding />,
  "cover-toolbar": <CoverToolbar />,
  "clash-settings": <ClashSettings />,
};

const scene = new URLSearchParams(location.search).get("scene") || "placecard";
createRoot(document.getElementById("root")).render(
  SCENES[scene] ?? <p style={{ color: "red", padding: 20 }}>Unknown scene: {scene}</p>,
);
