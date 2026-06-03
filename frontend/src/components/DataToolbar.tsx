import { useRef, useState } from "react";
import { api } from "../api";
import { useDropdown } from "../hooks/useDropdown";

type Props = {
  sessionId: number;
  colourByClass: boolean;
  onColourByClassChange: (v: boolean) => void;
  showAlerts: boolean;
  onShowAlertsChange: (v: boolean) => void;
  onImport: (kind: "session" | "qualifications" | "lecturer-preferences" | "overall-visual", file: File) => void;
  importing?: boolean;
};

export function DataToolbar({
  sessionId,
  colourByClass,
  onColourByClassChange,
  showAlerts,
  onShowAlertsChange,
  onImport,
  importing,
}: Props) {
  const exportMenu = useDropdown();
  const importMenu = useDropdown();
  const importRef = useRef<HTMLInputElement>(null);
  const [importKind, setImportKind] = useState<Props["onImport"] extends (k: infer K, f: File) => void ? K : never>("session");

  async function exportPath(path: string, filename: string) {
    exportMenu.close();
    await api.downloadExport(path, filename);
  }

  function pickImport(kind: typeof importKind) {
    setImportKind(kind);
    importMenu.close();
    importRef.current?.click();
  }

  return (
    <>
      <input
        ref={importRef}
        type="file"
        accept=".xlsm,.xlsx"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onImport(importKind, file);
          e.target.value = "";
        }}
      />
      <div className="tt-toolbar-group">
        <span className="tt-toolbar-label">Display</span>
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
      </div>
      <div className="tt-toolbar-group tt-dropdown-wrap" ref={importMenu.wrapRef}>
        <span className="tt-toolbar-label">Import</span>
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
          <div className="tt-dropdown-menu" role="menu">
            <button type="button" className="ctx-item" role="menuitem" onClick={() => pickImport("session")}>
              Session backup (.xlsm/.xlsx)
            </button>
            <button type="button" className="ctx-item" role="menuitem" onClick={() => pickImport("qualifications")}>
              Qualifications template
            </button>
            <button type="button" className="ctx-item" role="menuitem" onClick={() => pickImport("lecturer-preferences")}>
              Lecturer preferences
            </button>
            <button type="button" className="ctx-item" role="menuitem" onClick={() => pickImport("overall-visual")}>
              Overall visual grid
            </button>
          </div>
        )}
      </div>
      <div className="tt-toolbar-group tt-dropdown-wrap" ref={exportMenu.wrapRef}>
        <span className="tt-toolbar-label">Export</span>
        <button
          type="button"
          className="btn-secondary"
          onClick={exportMenu.toggle}
          aria-expanded={exportMenu.open}
          aria-haspopup="menu"
        >
          Export ▾
        </button>
        {exportMenu.open && (
          <div className="tt-dropdown-menu tt-dropdown-menu-wide" role="menu">
            <span className="ctx-label">Spreadsheets</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                void exportPath(
                  `/sessions/${sessionId}/export/timetable?variant=v2&colour_by_class=${colourByClass}`,
                  "timetable_export.xlsm",
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
              onClick={() => void exportPath(`/sessions/${sessionId}/export/admin`, "admin_export.xlsx")}
            >
              <span className="ctx-item-title">Admin export</span>
              <span className="ctx-item-hint">Term week grid for administrators</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() =>
                void exportPath(`/sessions/${sessionId}/export/admin?co_teach_only=true`, "co_teach_export.xlsx")
              }
            >
              <span className="ctx-item-title">SFS co-teach export</span>
              <span className="ctx-item-hint">Admin layout, co-teach classes only</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => void exportPath(`/sessions/${sessionId}/export/staff-tab`, "staff_tab.xlsx")}
            >
              <span className="ctx-item-title">Staff tab</span>
              <span className="ctx-item-hint">Lecturer hours spreadsheet</span>
            </button>
            <div className="ctx-divider" />
            <span className="ctx-label">Reports</span>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => void exportPath(`/sessions/${sessionId}/export/warnings`, "warnings_report.xlsx")}
            >
              <span className="ctx-item-title">Warnings report</span>
              <span className="ctx-item-hint">All validation warnings as Excel</span>
            </button>
            <button
              type="button"
              className="ctx-item ctx-item-desc"
              role="menuitem"
              onClick={() => void exportPath(`/sessions/${sessionId}/export/change-log`, "change_log_resolved.xlsx")}
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
                void api.exportSessionJson(sessionId);
              }}
            >
              <span className="ctx-item-title">JSON backup</span>
              <span className="ctx-item-hint">Machine-readable session snapshot</span>
            </button>
          </div>
        )}
      </div>
    </>
  );
}
