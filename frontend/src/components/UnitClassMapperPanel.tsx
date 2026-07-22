/** Unit-class mapper: pick a qualification, toggle its study-unit codes, and
 *  copy the selection grouped by class — "Class (unit1, unit2)" per line.
 *  Replicates the units-master spreadsheet lookup. */
import { useEffect, useMemo, useState } from "react";
import { api, type Qualification, type Unit } from "../api";

type Props = {
  sessionId: number;
  onError?: (message: string) => void;
};

type ClassRow = {
  id: number;
  name: string;
  codes: string[];
};

function splitCodes(raw: string | null | undefined): string[] {
  return (raw ?? "")
    .split(/[,;/]/)
    .map((c) => c.trim())
    .filter(Boolean);
}

export function UnitClassMapperPanel({ sessionId, onError }: Props) {
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [qualId, setQualId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [quals, unitRows] = await Promise.all([
          api.qualifications(sessionId),
          api.units(sessionId),
        ]);
        if (cancelled) return;
        setQualifications(quals);
        setUnits(unitRows);
        setQualId((prev) => prev ?? quals[0]?.id ?? null);
      } catch (err) {
        if (!cancelled) onError?.(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, onError]);

  const classes = useMemo<ClassRow[]>(() => {
    if (qualId == null) return [];
    return units
      .filter((u) => (u.qualification_ids ?? []).includes(qualId))
      .map((u) => ({ id: u.id, name: u.name, codes: splitCodes(u.component_codes) }))
      .filter((c) => c.codes.length > 0)
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [units, qualId]);

  const allCodes = useMemo(() => classes.flatMap((c) => c.codes), [classes]);

  // Reset the selection when switching qualification.
  useEffect(() => {
    setSelected(new Set());
  }, [qualId]);

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  const outputLines = useMemo(
    () =>
      classes
        .map((c) => ({ name: c.name, picked: c.codes.filter((code) => selected.has(code)) }))
        .filter((c) => c.picked.length > 0)
        .map((c) => `${c.name} (${c.picked.join(", ")})`),
    [classes, selected],
  );

  async function copyOutput() {
    try {
      const plain = outputLines.join("\n");
      const html = outputLines
        .map(
          (line) =>
            `<p style="font-family:Arial,sans-serif;font-size:13px;margin:0 0 4px;">${line
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")}</p>`,
        )
        .join("");
      if (navigator.clipboard && "write" in navigator.clipboard && typeof ClipboardItem !== "undefined") {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([plain], { type: "text/plain" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(plain);
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Copy failed");
    }
  }

  return (
    <section className="panel unit-mapper-panel">
      <div className="unit-mapper-toolbar">
        <h2>Unit-class mapper</h2>
        <label className="unit-mapper-qual">
          Qualification
          <select
            className="field-select"
            value={qualId ?? ""}
            onChange={(e) => setQualId(e.target.value === "" ? null : Number(e.target.value))}
          >
            {qualifications.map((q) => (
              <option key={q.id} value={q.id}>
                {q.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn-secondary btn-xs"
          disabled={!allCodes.length}
          onClick={() => setSelected(new Set(allCodes))}
        >
          Select all
        </button>
        <button
          type="button"
          className="btn-secondary btn-xs"
          disabled={!selected.size}
          onClick={() => setSelected(new Set())}
        >
          Clear
        </button>
        <span className="muted">{selected.size} selected</span>
      </div>

      {loading && <p className="panel-empty">Loading…</p>}
      {!loading && !classes.length && (
        <p className="panel-empty">
          No classes with study-unit codes are linked to this qualification.
        </p>
      )}

      {!loading && classes.length > 0 && (
        <>
          <p className="muted entity-hint">
            Click the study units to select them, then copy — the output lists each class
            with its selected units.
          </p>
          <div className="unit-mapper-classes">
            {classes.map((c) => (
              <div key={c.id} className="unit-mapper-class">
                <span className="unit-mapper-class-name" title={c.name}>
                  {c.name}
                </span>
                <div className="unit-mapper-codes">
                  {c.codes.map((code) => (
                    <button
                      key={`${c.id}-${code}`}
                      type="button"
                      className={`unit-mapper-code${selected.has(code) ? " unit-mapper-code--on" : ""}`}
                      onClick={() => toggle(code)}
                    >
                      {code}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="unit-mapper-output">
            <div className="unit-mapper-output-head">
              <span className="unit-mapper-output-label">Output</span>
              <button
                type="button"
                className="btn-primary"
                disabled={!outputLines.length}
                onClick={() => void copyOutput()}
              >
                {copied ? "Copied ✓" : "Copy to clipboard"}
              </button>
            </div>
            <pre className="unit-mapper-preview">
              {outputLines.length ? outputLines.join("\n") : "(select study units above)"}
            </pre>
          </div>
        </>
      )}
    </section>
  );
}
