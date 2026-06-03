import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { LinkedImportPickerModal, type ImportPickerItem } from "./LinkedImportPickerModal";

type LinkedSession = { id: number; name: string };

type PickerKind = "staff" | "qualifications" | null;

type Props = {
  targetSessionId: number;
  targetOptions?: LinkedSession[];
  onImported?: () => void;
  importStaff?: boolean;
  importQualifications?: boolean;
};

export function LinkedSessionImportPanel({
  targetSessionId,
  targetOptions,
  onImported,
  importStaff = true,
  importQualifications = true,
}: Props) {
  const [linked, setLinked] = useState<LinkedSession[]>([]);
  const [targetId, setTargetId] = useState(targetSessionId);
  const [sourceId, setSourceId] = useState<number | "">("");
  const [wantStaff, setWantStaff] = useState(false);
  const [wantQual, setWantQual] = useState(false);
  const [picker, setPicker] = useState<PickerKind>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [staffOptions, setStaffOptions] = useState<ImportPickerItem[]>([]);
  const [qualOptions, setQualOptions] = useState<ImportPickerItem[]>([]);
  const [selectedStaffIds, setSelectedStaffIds] = useState<number[]>([]);
  const [selectedQualIds, setSelectedQualIds] = useState<number[]>([]);
  const [linkedLoading, setLinkedLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadLinked = useCallback(async () => {
    setLinkedLoading(true);
    try {
      const data = await api.linkedSessions(targetId);
      setLinked(data.sessions);
      setSourceId((prev) => {
        if (prev !== "" && data.sessions.some((s) => s.id === prev)) return prev;
        return data.sessions[0]?.id ?? "";
      });
    } catch {
      setLinked([]);
      setSourceId("");
    } finally {
      setLinkedLoading(false);
    }
  }, [targetId]);

  const loadOptions = useCallback(async () => {
    if (sourceId === "") return;
    setOptionsLoading(true);
    try {
      const data = await api.linkedImportOptions(targetId, Number(sourceId));
      setStaffOptions(data.staff);
      setQualOptions(data.qualifications);
    } catch {
      setStaffOptions([]);
      setQualOptions([]);
    } finally {
      setOptionsLoading(false);
    }
  }, [targetId, sourceId]);

  useEffect(() => {
    setTargetId(targetSessionId);
  }, [targetSessionId]);

  useEffect(() => {
    void loadLinked();
  }, [loadLinked]);

  useEffect(() => {
    setSelectedStaffIds([]);
    setSelectedQualIds([]);
    setWantStaff(false);
    setWantQual(false);
    void loadOptions();
  }, [loadOptions, sourceId, targetId]);

  function openPicker(kind: PickerKind) {
    if (sourceId === "") {
      setError("Choose a source session first.");
      return;
    }
    setPicker(kind);
  }

  function onStaffCheckbox(checked: boolean) {
    setWantStaff(checked);
    if (checked) openPicker("staff");
    else setSelectedStaffIds([]);
  }

  function onQualCheckbox(checked: boolean) {
    setWantQual(checked);
    if (checked) openPicker("qualifications");
    else setSelectedQualIds([]);
  }

  async function runImport() {
    if (sourceId === "") return;
    if (!selectedStaffIds.length && !selectedQualIds.length) {
      setError("Select staff and/or qualifications to import.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.importFromLinkedSession(targetId, {
        source_session_id: Number(sourceId),
        staff_ids: selectedStaffIds,
        qualification_ids: selectedQualIds,
      });
      const parts: string[] = [];
      if (result.staff) {
        parts.push(
          `Staff: ${result.staff.added.length} added` +
            (result.staff.skipped.length ? `, ${result.staff.skipped.length} skipped` : ""),
        );
      }
      if (result.qualifications) {
        let qualPart =
          `Qualifications: ${result.qualifications.added.length} added` +
          (result.qualifications.skipped.length
            ? `, ${result.qualifications.skipped.length} skipped`
            : "");
        if (result.qualifications.classes_added?.length) {
          qualPart += `; ${result.qualifications.classes_added.length} class(es)`;
        }
        parts.push(qualPart);
      }
      setMessage(parts.join(" · ") || "Nothing imported.");
      setSelectedStaffIds([]);
      setSelectedQualIds([]);
      setWantStaff(false);
      setWantQual(false);
      onImported?.();
      void loadOptions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  if (linkedLoading && !linked.length) {
    return <p className="muted entity-hint">Checking linked sessions…</p>;
  }

  if (!linked.length) {
    return (
      <p className="muted entity-hint">
        Link at least two timetable sessions in this global group to import staff or qualifications
        between them.
      </p>
    );
  }

  const targets = targetOptions?.length
    ? targetOptions
    : [{ id: targetSessionId, name: "This session" }];

  return (
    <>
      <section className="linked-import-panel card">
        <h3>Import from linked session</h3>
        <p className="muted entity-hint">
          Choose a source session, tick staff or qualifications, then pick exactly which rows to
          copy. Qualifications are imported with one group and their linked classes.
        </p>
        <div className="linked-import-fields">
          {targetOptions && targetOptions.length > 1 && (
            <label>
              Into session
              <select
                className="field-select"
                value={targetId}
                onChange={(e) => {
                  setTargetId(Number(e.target.value));
                  setSourceId("");
                }}
              >
                {targets.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            From session
            <select
              className="field-select"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              {linked.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="linked-import-type-rows">
          {importStaff && (
            <div className="linked-import-type-row">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={wantStaff}
                  onChange={(e) => onStaffCheckbox(e.target.checked)}
                />
                Staff
              </label>
              <button
                type="button"
                className="btn-secondary btn-xs"
                disabled={!wantStaff}
                onClick={() => openPicker("staff")}
              >
                {selectedStaffIds.length
                  ? `${selectedStaffIds.length} selected — change`
                  : "Choose staff…"}
              </button>
            </div>
          )}
          {importQualifications && (
            <div className="linked-import-type-row">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={wantQual}
                  onChange={(e) => onQualCheckbox(e.target.checked)}
                />
                Qualifications (+ linked classes)
              </label>
              <button
                type="button"
                className="btn-secondary btn-xs"
                disabled={!wantQual}
                onClick={() => openPicker("qualifications")}
              >
                {selectedQualIds.length
                  ? `${selectedQualIds.length} selected — change`
                  : "Choose qualifications…"}
              </button>
            </div>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        {message && <p className="message-banner">{message}</p>}
        <button
          type="button"
          className="btn-primary"
          disabled={busy || (!selectedStaffIds.length && !selectedQualIds.length)}
          onClick={() => void runImport()}
        >
          {busy ? "Importing…" : "Import selected"}
        </button>
      </section>

      {picker === "staff" && (
        <LinkedImportPickerModal
          title="Select staff to import"
          description="Copy lecturer details, availability, and preferences into the target session."
          items={staffOptions}
          loading={optionsLoading}
          onClose={() => {
            setPicker(null);
            if (!selectedStaffIds.length) setWantStaff(false);
          }}
          onConfirm={(ids) => {
            setSelectedStaffIds(ids);
            setWantStaff(ids.length > 0);
            setPicker(null);
          }}
        />
      )}

      {picker === "qualifications" && (
        <LinkedImportPickerModal
          title="Select qualifications to import"
          description="Each qualification is created with one group. Linked classes are copied or attached in the target session."
          items={qualOptions}
          loading={optionsLoading}
          onClose={() => {
            setPicker(null);
            if (!selectedQualIds.length) setWantQual(false);
          }}
          onConfirm={(ids) => {
            setSelectedQualIds(ids);
            setWantQual(ids.length > 0);
            setPicker(null);
          }}
        />
      )}
    </>
  );
}
