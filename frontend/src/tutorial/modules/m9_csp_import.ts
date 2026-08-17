/** Module 9 — import a qualification CSP document.
 *
 * Teaches with a real file through the real importer: the step offers a
 * generated sample CSP, and verification checks the qualification actually
 * arrived — not that a dialog was clicked.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

/** Must match SAMPLE_CSP_QUALIFICATION in the backend's sample_files.py. */
const SAMPLE_QUAL = "22334VIC Certificate IV in Cyber Operations";

export const m9CspImport: TutorialModule = {
  id: "m9_csp_import",
  title: "Import a qualification CSP",
  section: "Tutorial 2 — Running the timetable",
  goal: "Bring a whole qualification in from a CSP document in one import.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable`,
  steps: [
    {
      id: "what-a-csp",
      title: "What a CSP gives you",
      body:
        "A CSP — course study plan — is the Word document a qualification arrives as: semester tables listing each class, its hours, and its unit codes.\n\nRather than typing all of that in, you import the document — one qualification is created with every class linked, hours converted to timetable lengths, and unit codes attached.\n\nDownload the sample CSP below and open it to see the shape: two semester tables, six classes, one of them carrying two unit codes.",
      advance: "next",
      download: {
        label: "Download the sample CSP (.docx)",
        kind: "csp",
        filename: "CSP_22334VIC Certificate IV in Cyber Operations.docx",
      },
    },
    {
      id: "run-the-import",
      title: "Import it",
      body:
        "Open Import ▾ in the top toolbar and choose \"Qualifications CSP\", then pick the file you just downloaded.\n\nThe import reads every semester table into one qualification — splitting it into stages is a decision you make afterwards, in the Qualifications tab, not something the document decides for you.",
      advance: "verify",
      target: "import-menu",
      watch: { api: /\/import\// },
      verify: async (ctx) => {
        const quals = await api.qualifications(ctx.sessionId);
        return quals.some((q) => q.name === SAMPLE_QUAL);
      },
      hint: "Import ▾ → Qualifications CSP → choose the downloaded .docx. The report tells you how many classes were created.",
    },
    {
      id: "inspect-the-result",
      title: "See what arrived",
      body:
        "Open the Qualifications tab and select 22334VIC Certificate IV in Cyber Operations. All six classes are linked, and Networking Essentials carries both its unit codes.\n\nFrom here the Stage split button deals the classes into stages when you're ready to timetable them separately — the import never guesses that for you.",
      advance: "verify",
      target: "tab-qualifications",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "qualifications",
    },
  ],
  recap: [
    "Import ▾ → Qualifications CSP turns the Word document into a qualification with every class linked.",
    "Hours in the document become class lengths on the timetable.",
    "One qualification per document — stage splitting is your call, made later.",
  ],
};
