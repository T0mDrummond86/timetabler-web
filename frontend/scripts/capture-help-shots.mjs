/** Capture the annotated screenshots used by the help articles.
 *
 * Shoots the scenes in scripts/help-shots.jsx — the app's own components and
 * stylesheet with stand-in data — rather than a live session. Driving the real
 * app headlessly needs an authenticated session, and the only way to get one
 * was to weaken auth on the dev stack; not worth it for illustrations.
 *
 * The red marker is an absolutely-positioned overlay drawn over the element's
 * own bounding box just before the capture, not an edit to the image
 * afterwards, so it always lands exactly on the control however the layout has
 * shifted since the shot was last taken.
 *
 * Re-runnable. After changing a component, re-run this and the pictures follow.
 *
 *   cd frontend && node scripts/capture-help-shots.mjs          # all
 *   cd frontend && node scripts/capture-help-shots.mjs holding  # just one
 *
 * Needs the dev server up (docker compose up -d frontend) and Google Chrome.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const OUT_DIR = path.join(ROOT, "public/help");

const APP = process.env.HELP_APP_URL || "http://localhost:5173";
const HARNESS = `${APP}/scripts/help-shots.html`;
const CHROME =
  process.env.HELP_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

/** The help panel's content column, measured in the running app.
 *
 * Everything is displayed at this width, so a capture much wider than twice it
 * arrives squeezed and unreadable. Crops are kept tight and deliberately
 * narrow: better to show the one control the article is about than the whole
 * bar it sits in.
 */
const PANEL_WIDTH = 366;

/** 2x device scale, so a 366px crop lands as a 732px PNG and stays crisp. */
const DEVICE_SCALE = 2;

const VIEWPORT = { width: 1200, height: 800, deviceScaleFactor: DEVICE_SCALE };

/** Viewport for scenes whose component is naturally wider than the panel.
 *
 * Cropping a 1400px-wide tab strip down to fit would either truncate it or
 * shrink the text to half size. Laying it out in a narrow window instead lets
 * the component wrap the way it does on a small screen, so the capture is both
 * complete and legible at the width it will actually be shown.
 */
const NARROW = { width: 470, height: 900, deviceScaleFactor: DEVICE_SCALE };

/**
 *   id      output file name
 *   scene   ?scene= in the harness
 *   click   optional button text to press first (opens a menu)
 *   ring    selector to outline in red
 *   pad     context kept around the ring, in CSS px
 *   alt     alt text, written into the article
 */
const SHOTS = [
  {
    id: "placecard",
    scene: "placecard",
    ring: ".booking-card",
    pad: 26,
    alt: "A placecard showing the time, class name, lecturer and room",
  },
  {
    id: "placecard-locked",
    scene: "placecard-locked",
    ring: ".booking-card",
    pad: 26,
    alt: "A locked placecard, showing the padlock badge beside the class name",
  },
  {
    id: "placecard-warning",
    scene: "placecard-warning",
    // ring: none -- the red border is the subject; see PlacecardPair.
    ring: ".scene",
    pad: 0,
    annotate: false,
    alt: "A normal placecard beside one with the red border that marks a hard clash",
  },
  {
    id: "toolbar-import",
    scene: "toolbar-import",
    click: "Import",
    ring: ".tt-dropdown-menu",
    pad: 12,
    alt: "The Import menu open, listing Session backup, Qualifications CSP, EP-NB CSP and aSc export",
  },
  {
    id: "toolbar-export",
    scene: "toolbar-export",
    click: "Export",
    ring: ".tt-dropdown-menu",
    pad: 12,
    alt: "The Export menu open, listing Timetable, Admin export, Print timetables and JSON backup",
  },
  {
    id: "holding-area",
    viewport: NARROW,
    scene: "holding",
    ring: ".holding-panel",
    pad: 14,
    alt: "The holding area, listing classes that are not yet scheduled",
  },
  {
    id: "cover-week-beginning",
    scene: "cover-toolbar",
    ring: ".cover-request-date",
    pad: 90,
    alt: "The Week beginning date box on the Lecturer cover tab",
  },
  {
    id: "staff-hours",
    scene: "hours",
    ring: ".staff-col-variance",
    crop: ".staff-hours-table-wrap, table",
    pad: 8,
    maxHeight: 420,
    alt: "The lecturer hours table, with a green over-hours and a red under-hours variance badge",
  },
  {
    id: "staff-availability",
    scene: "availability",
    ring: ".staff-availability-grid",
    pad: 10,
    maxHeight: 300,
    alt: "The availability grid, with blocked half-hour slots ticked",
  },
  {
    id: "class-custodians",
    scene: "custodians",
    ring: ".data-table, table",
    pad: 10,
    alt: "The class custodians table, showing who owns each class",
  },
  {
    id: "toolbar-display",
    scene: "toolbar-display",
    click: "Display",
    ring: ".tt-dropdown-menu",
    pad: 12,
    alt: "The Display menu, with colour by class, show alerts, auto clash detect and grid zoom",
  },
  {
    id: "changelog",
    scene: "changelog",
    ring: ".change-log-toolbar",
    pad: 10,
    alt: "The Change log toolbar, with the resolved view and the copy-for-email actions",
  },
  {
    id: "warnings-report",
    scene: "warnings",
    viewport: NARROW,
    ring: ".violations-report-panel",
    pad: 10,
    maxHeight: 420,
    alt: "The Warnings tab, listing violations with the hard and soft filter",
  },
  {
    id: "clash-settings",
    scene: "clash-settings-real",
    viewport: NARROW,
    ring: ".clash-settings-group",
    pad: 10,
    maxHeight: 420,
    alt: "Clash settings, with each check listed under its category and a tick to enable it",
  },
  {
    id: "stage-split",
    viewport: NARROW,
    scene: "stage-split",
    ring: ".stage-split-count",
    crop: ".stage-split-card",
    pad: 8,
    maxHeight: 420,
    alt: "The Stage split dialog, with the number of stages and the class assignment table",
  },
  {
    id: "quals-merge",
    viewport: NARROW,
    scene: "merge",
    select: { selector: ".qual-merge-card select", value: "2" },
    ring: ".qual-merge-outcome",
    crop: ".qual-merge-card",
    pad: 8,
    maxHeight: 460,
    alt: "The Merge dialog, showing both source qualifications and what the merged one will hold",
  },
];

/** Injected into the page: draw the marker, report the crop rectangle.
 *
 * `cropSelector` lets the crop be anchored somewhere other than the marker.
 * Ringing one column of a table is the case that needs it: centring the crop
 * on the marker slices the row labels in half, which reads as a mistake rather
 * than as a close-up.
 */
function ringAndMeasure(selector, pad, maxWidth, annotate, maxHeight, cropSelector) {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const cropEl = cropSelector ? document.querySelector(cropSelector) : null;
  const cr = cropEl ? cropEl.getBoundingClientRect() : r;

  const ring = annotate ? document.createElement("div") : null;
  if (ring) {
  Object.assign(ring.style, {
    position: "fixed",
    left: `${r.left - 3}px`,
    top: `${r.top - 3}px`,
    width: `${r.width + 6}px`,
    height: `${r.height + 6}px`,
    border: "2.5px solid #ef4444",
    borderRadius: "8px",
    boxShadow: "0 0 0 2px rgba(239,68,68,0.25)",
    pointerEvents: "none",
    zIndex: "2147483647",
  });
  ring.setAttribute("data-help-ring", "1");
  document.body.appendChild(ring);
  }

  const x = Math.max(0, cr.left - pad);
  const y = Math.max(0, cr.top - pad);
  const wanted = cr.width + pad * 2;
  const width = Math.min(maxWidth, Math.min(window.innerWidth - x, wanted));
  const height = Math.min(
    maxHeight || Infinity,
    Math.min(window.innerHeight - y, cr.height + pad * 2),
  );
  return { x, y, width, height, truncated: width < wanted - 1 };
}

async function main() {
  const only = process.argv[2];
  const puppeteer = await import("puppeteer-core");
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox"],
    defaultViewport: VIEWPORT,
  });

  try {
    const page = await browser.newPage();
    await mkdir(OUT_DIR, { recursive: true });
    const written = [];

    for (const shot of SHOTS) {
      if (only && shot.id !== only) continue;
      await page.setViewport(shot.viewport ?? VIEWPORT);
      await page.goto(`${HARNESS}?scene=${shot.scene}`, { waitUntil: "networkidle2" });
      await new Promise((r) => setTimeout(r, 500));

      if (shot.click) {
        await page.evaluate((label) => {
          const btn = [...document.querySelectorAll("button")].find((b) =>
            b.textContent.includes(label),
          );
          if (btn) btn.click();
        }, shot.click);
        await new Promise((r) => setTimeout(r, 300));
      }

      // Some dialogs only show anything once a choice is made -- the merge
      // preview does not load until the second qualification is picked. React
      // ignores a plain value assignment, so the native setter is used and the
      // change event raised by hand.
      if (shot.select) {
        await page.evaluate(({ selector, value }) => {
          const el = document.querySelector(selector);
          if (!el) return;
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLSelectElement.prototype,
            "value",
          ).set;
          setter.call(el, value);
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }, shot.select);
        await new Promise((r) => setTimeout(r, 700));
      }

      try {
        await page.waitForSelector(shot.ring, { timeout: 8000 });
      } catch {
        console.warn(`  ! ${shot.id}: no element matching ${shot.ring} -- skipped`);
        continue;
      }
      const clip = await page.evaluate(
        ringAndMeasure,
        shot.ring,
        shot.pad,
        PANEL_WIDTH * 2,
        shot.annotate !== false,
        shot.maxHeight,
        shot.crop,
      );
      if (!clip || clip.width < 20 || clip.height < 20) {
        console.warn(`  ! ${shot.id}: could not measure ${shot.ring}, skipped`);
        continue;
      }

      if (clip.truncated) {
        console.warn(
          `  ! ${shot.id}: ${shot.ring} is wider than the crop, so the marker is cut off. ` +
            `Give this shot a narrower viewport.`,
        );
      }
      const buffer = await page.screenshot({ clip, type: "png" });
      await writeFile(path.join(OUT_DIR, `${shot.id}.png`), buffer);
      written.push({ ...shot, bytes: buffer.length, clip });
      console.log(
        `  ${shot.id}.png  ${Math.round(clip.width * DEVICE_SCALE)}x` +
          `${Math.round(clip.height * DEVICE_SCALE)}  ${(buffer.length / 1024).toFixed(0)} kB`,
      );
    }

    console.log("\nMarkdown:");
    for (const w of written) console.log(`![${w.alt}](/help/${w.id}.png)`);
    console.log(`\n${written.length} shot(s) -> ${path.relative(ROOT, OUT_DIR)}`);
  } finally {
    await browser.close();
  }
}

await main();
