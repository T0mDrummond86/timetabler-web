import { useRef, useState } from "react";
import { api } from "../api";
import { useDelayedBusy } from "../hooks/useDelayedBusy";
import { useDropdown } from "../hooks/useDropdown";
import { LoadingMark } from "./LoadingMark";
import { TimetablePrintDialog } from "./TimetablePrintDialog";
import { QualificationClusterExportDialog } from "./QualificationClusterExportDialog";

type Props = {
  sessionId: number;
  colourByClass: boolean;
  onColourByClassChange: (v: boolean) => void;
  showAlerts: boolean;
  onShowAlertsChange: (v: boolean) => void;
  autoClashDetect: boolean;
  onAutoClashDetectChange: (v: boolean) => void;
  onCheckClashes?: () => void;
  checkingClashes?: boolean;
  onImport: (kind: "session" | "qualifications" | "qualifications-csp" | "qualifications-ep-nb-csp" | "asc" | "lecturer-preferences" | "overall-visual" | "admin-visual", file: File) => void;
  onError?: (message: string) => void;
  importing?: boolean;
  showDisplay?: boolean;
};

export function DataToolbar({
  sessionId,
  colourByClass,
  onColourByClassChange,
  showAlerts,
  onShowAlertsChange,
  autoClashDetect,
  onAutoClashDetectChange,
  onCheckClashes,
  checkingClashes = false,
  onImport,
  onError,
  importing,
  showDisplay = true,
}: Props) {
  const exportMenu = useDropdown();
  const importMenu = useDropdown();
  const importRef = useRef<HTMLInputElement>(null);
  type ImportKind = Props["onImport"] extends (k: infer K, f: File) => void ? K : never;
  const importKindRef = useRef<ImportKind>("session");
  const [importKind, setImportKind] = useState<ImportKind>("session");
  const [printOpen, setPrintOpen] = useState(false);
  const [clusterExportOpen, setClusterExportOpen] = useState(false);
  const [exportLabel, setExportLabel] = useState("");
  const { busy: exporting, showBusy: showExportOverlay, run: runExport } = useDelayedBusy(5000);

  function importAcceptFor(kind: ImportKind) {
    if (kind === "qualifications-csp") return ".docx";
    if (kind === "qualifications-ep-nb-csp") return ".xlsx";
    if (kind === "asc") return ".xlsm,.xlsx,.xml";
    return ".xlsm,.xlsx";
  }

  const importAccept = importAcceptFor(importKind);

  function exportPath(path: string, filename: string, label: string) {
    exportMenu.close();
    setExportLabel(label);
    void runExport(async () => {
      try {
        await api.downloadExport(path, filename);
      } catch (err) {
        onError?.(err instanceof Error ? err.message : "Export failed");
        throw err;
      }
    });
  }

  function pickImport(kind: ImportKind) {
    importKindRef.current = kind;
    setImportKind(kind);
    importMenu.close();
    const input = importRef.current;
    if (!input) return;
    input.accept = importAcceptFor(kind);
    input.click();
  }

  return (
    <>
      <input
        ref={importRef}
        type="file"
        accept={importAccept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onImport(importKindRef.current, file);
          e.target.value = "";
        }}
      />
      {showDisplay && (
        <div className="tt-toolbar-group">
          <span className="tt-toolbar-label">View</span>
          <label className="checkbox tt-toolbar-check">
            <input
              type="checkbox"
              checked={colourByClass}
              onChange={(e) => onColourByClassChange(e.target.checked)}
            />
            Class colours
          </label>
          <label className="checkbox tt-toolbar-check">
            <input
              type="checkbox"
              checked={showAlerts}
              onChange={(e) => onShowAlertsChange(e.target.checked)}
            />
            Alerts
          </label>
          <label className="checkbox tt-toolbar-check" title="When off, clashes are not checked after each move — use Check clashes to run once">
            <input
              type="checkbox"
              checked={autoClashDetect}
              onChange={(e) => onAutoClashDetectChange(e.target.checked)}
            />
            Auto-detect clashes
          </label>
          {!autoClashDetect && onCheckClashes && (
            <button
              type="button"
              className="btn-secondary btn-xs"
              onClick={onCheckClashes}
              disabled={checkingClashes}
              title="Run one full clash check on the current week"
            >
              {checkingClashes ? "Checking…" : "Check clashes"}
            </button>
          )}
        </div>
      )}
      <div className="tt-toolbar-group">
        <span className="tt-toolbar-label">Data</span>
        <span className="tt-dropdown-wrap" ref={importMenu.wrapRef}>
        <button
          type="button"
          className="btn-secondary"
          onClick={importMenu.toggle}
          disabled={importing}
          aria-expanded={importMenu.open}
          aria-haspopup="menu"
        >
          {importing ? "Importing…" : "Import ▾"}
        </button>
        {importMenu.open && (
          <div className="tt-dropdown-menu tt-dropdown-menu-wide" role="menu">
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("session")}>
              <span className="ctx-item-title">Session backup</span>
              <span className="ctx-item-hint">Full round-trip restore (.xlsm / .xlsx)</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("qualifications")}>
              <span className="ctx-item-title">Qualifications template</span>
              <span className="ctx-item-hint">QInputTemplate classes &amp; quals</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("qualifications-csp")}>
              <span className="ctx-item-title">Qualifications CSP</span>
              <span className="ctx-item-hint">Curriculum Structure Package (.docx)</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("qualifications-ep-nb-csp")}>
              <span className="ctx-item-title">EP-NB CSP</span>
              <span className="ctx-item-hint">East Perth / Northbridge CSP spreadsheet (.xlsx)</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("asc")}>
              <span className="ctx-item-title">aSc export</span>
              <span className="ctx-item-hint">Staff, rooms, classes, quals &amp; bookings from aSc (.xlsx / .xml)</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("lecturer-preferences")}>
              <span className="ctx-item-title">Lecturer preferences</span>
              <span className="ctx-item-hint">Availability &amp; competency spreadsheet</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("overall-visual")}>
              <span className="ctx-item-title">Overall visual grid</span>
              <span className="ctx-item-hint">Legacy Joondalup Overall sheet</span>
            </button>
            <button type="button" className="ctx-item ctx-item-desc" role="menuitem" onClick={() => pickImport("admin-visual")}>
              <span className="ctx-item-title">Admin export (visual grid)</span>
              <span className="ctx-item-hint">Course tabs with week bands — replaces bookings</span>
            </button>
          </div>
        )}
        </span>
        <span className="tt-dropdown-wrap" ref={exportMenu.wrapRef}>
        <button
          type="button"
          className="btn-secondary"
          onClick={exportMenu.toggle}
          disabled={exporting}
          aria-expanded={exportMenu.open}
          aria-haspopup="menu"
        >
          {exporting ? "Exporting…" : "Export ▾"}
        </button>
        {exportMenu.open && (
          <div className="tt-dropdown-menu tt-dropdown-menu-wide" role="menu">
            <span className="ctx-label">Spreadsheets</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                exportPath(
                  `/sessions/${sessionId}/export/timetable?variant=v2&colour_by_class=${colourByClass}`,
                  "timetable_export.xlsm",
                  "Timetable",
                )
              }
            >
              <span className="ctx-item-title">Timetable</span>
              <span className="ctx-item-hint">Per course, lecturer, and room (.xlsm)</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => void exportPath(`/sessions/${sessionId}/export/admin`, "admin_export.xlsx", "Admin export")}
            >
              <span className="ctx-item-title">Admin export</span>
              <span className="ctx-item-hint">Term week grid for administrators</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                void exportPath(
                  `/sessions/${sessionId}/export/admin?changed_only=true`,
                  "admin_export_changes.xlsx",
                  "Admin export (changes only)",
                )
              }
            >
              <span className="ctx-item-title">Admin export (changes only)</span>
              <span className="ctx-item-hint">Only courses with logged changes</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => void exportPath(`/sessions/${sessionId}/export/staff-tab`, "staff_tab.xlsx", "Staff tab")}
            >
              <span className="ctx-item-title">Staff tab</span>
              <span className="ctx-item-hint">Lecturer hours spreadsheet</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => {
                exportMenu.close();
                setClusterExportOpen(true);
              }}
            >
              <span className="ctx-item-title">Qualification clusters…</span>
              <span className="ctx-item-hint">Selected qualifications, one tab each (clusters + units)</span>
            </button>
            <div className="ctx-divider" />
            <span className="ctx-label">Print</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => {
                exportMenu.close();
                setPrintOpen(true);
              }}
            >
              <span className="ctx-item-title">Print timetables…</span>
              <span className="ctx-item-hint">PDF — course, staff, or room (A4 landscape)</span>
            </button>
            <div className="ctx-divider" />
            <span className="ctx-label">Reports</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                void exportPath(
                  `/sessions/${sessionId}/export/change-log`,
                  "change_log_resolved.xlsx",
                  "Change log",
                )
              }
            >
              <span className="ctx-item-title">Change log</span>
              <span className="ctx-item-hint">Resolved net changes</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                void exportPath(
                  `/sessions/${sessionId}/export/lecturer-preferences-template`,
                  "lecturer_preferences.xlsx",
                  "Lecturer prefs template",
                )
              }
            >
              <span className="ctx-item-title">Lecturer prefs template</span>
              <span className="ctx-item-hint">Blank template for preferences import</span>
            </button>
            <div className="ctx-divider" />
            <span className="ctx-label">Backup</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => {
                exportMenu.close();
                setExportLabel("JSON backup");
                void runExport(async () => {
                  try {
                    await api.exportSessionJson(sessionId);
                  } catch (err) {
                    onError?.(err instanceof Error ? err.message : "Export failed");
                    throw err;
                  }
                });
              }}
            >
              <span className="ctx-item-title">JSON backup</span>
              <span className="ctx-item-hint">Machine-readable session snapshot</span>
            </button>
          </div>
        )}
        </span>
      </div>
      {printOpen && (
        <TimetablePrintDialog
          sessionId={sessionId}
          colourByClass={colourByClass}
          onClose={() => setPrintOpen(false)}
        />
      )}
      {clusterExportOpen && (
        <QualificationClusterExportDialog
          sessionId={sessionId}
          onClose={() => setClusterExportOpen(false)}
          onError={onError}
        />
      )}
      {showExportOverlay && (
        <div className="import-overlay" role="alertdialog" aria-busy="true" aria-labelledby="export-overlay-title">
          <div className="import-overlay-card">
            <LoadingMark size={88} label="" />
            <h2 id="export-overlay-title">Exporting{exportLabel ? ` ${exportLabel.toLowerCase()}` : ""}…</h2>
            <p>Large timetables can take a minute or more to prepare.</p>
          </div>
        </div>
      )}
    </>
  );
}
