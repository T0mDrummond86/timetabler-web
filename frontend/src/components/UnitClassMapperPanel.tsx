/** Unit-class mapper: find the qualification(s) a list of study units belongs
 *  to, and copy the result grouped by class — "Class (unit1, unit2)" per line.
 *  Replicates the units-master spreadsheet lookup, either by browsing a
 *  qualification or by pasting a raw list of unit codes. */
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

/** One qualification the pasted list resolved to, with the codes it covers. */
type QualMatch = {
  qualId: number;
  name: string;
  codes: string[];
};

function splitCodes(raw: string | null | undefined): string[] {
  return (raw ?? "")
    .split(/[,;/]/)
    .map((c) => c.trim())
    .filter(Boolean);
}

/** Accept newline, comma, tab or space separated codes, in any case. */
function parsePastedCodes(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const token of raw.split(/[\s,;]+/)) {
    const code = token.trim().toUpperCase();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    out.push(code);
  }
  return out;
}

/**
 * Work out which qualification(s) a pasted list of codes describes.
 *
 * Greedy set cover: repeatedly take the qualification covering the most
 * still-unclaimed codes. A code shared by two qualifications therefore lands
 * with whichever one the *rest* of the list points at, which is what makes an
 * ambiguous unit resolvable from its context.
 */
function matchQualifications(
  wanted: string[],
  codeToQuals: Map<string, Set<number>>,
  qualNames: Map<number, string>,
): { matches: QualMatch[]; unmatched: string[] } {
  const unmatched = wanted.filter((c) => !codeToQuals.has(c));
  let remaining = wanted.filter((c) => codeToQuals.has(c));
  const matches: QualMatch[] = [];

  while (remaining.length) {
    const tally = new Map<number, string[]>();
    for (const code of remaining) {
      for (const qid of codeToQuals.get(code) ?? []) {
        const list = tally.get(qid);
        if (list) list.push(code);
        else tally.set(qid, [code]);
      }
    }
    if (!tally.size) break;
    // Most codes wins; ties break on the lower id so the result is stable.
    let bestId = -1;
    let bestCodes: string[] = [];
    for (const [qid, codes] of tally) {
      if (
        codes.length > bestCodes.length ||
        (codes.length === bestCodes.length && bestId !== -1 && qid < bestId)
      ) {
        bestId = qid;
        bestCodes = codes;
      }
    }
    if (bestId === -1) break;
    matches.push({
      qualId: bestId,
      name: qualNames.get(bestId) ?? `Qualification #${bestId}`,
      codes: bestCodes,
    });
    const claimed = new Set(bestCodes);
    remaining = remaining.filter((c) => !claimed.has(c));
  }

  return { matches, unmatched };
}

export function UnitClassMapperPanel({ sessionId, onError }: Props) {
  const [qualifications, setQualifications] = useState<Qualification[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [qualId, setQualId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [pasted, setPasted] = useState("");
  const [matches, setMatches] = useState<QualMatch[] | null>(null);
  const [unmatched, setUnmatched] = useState<string[]>([]);

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

  /** Classes with study-unit codes, indexed by qualification. */
  const classesByQual = useMemo(() => {
    const out = new Map<number, ClassRow[]>();
    for (const u of units) {
      const codes = splitCodes(u.component_codes);
      if (!codes.length) continue;
      for (const qid of u.qualification_ids ?? []) {
        const row: ClassRow = { id: u.id, name: u.name, codes };
        const list = out.get(qid);
        if (list) list.push(row);
        else out.set(qid, [row]);
      }
    }
    for (const list of out.values()) list.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  }, [units]);

  const codeToQuals = useMemo(() => {
    const out = new Map<string, Set<number>>();
    for (const [qid, rows] of classesByQual) {
      for (const row of rows) {
        for (const code of row.codes) {
          const key = code.toUpperCase();
          const set = out.get(key);
          if (set) set.add(qid);
          else out.set(key, new Set([qid]));
        }
      }
    }
    return out;
  }, [classesByQual]);

  const qualNames = useMemo(
    () => new Map(qualifications.map((q) => [q.id, q.name])),
    [qualifications],
  );

  // Which qualifications the panel is showing: the matched ones after a paste,
  // otherwise just the one picked from the dropdown.
  const shownQualIds = useMemo(() => {
    if (matches) return matches.map((m) => m.qualId);
    return qualId == null ? [] : [qualId];
  }, [matches, qualId]);

  const allCodes = useMemo(
    () => shownQualIds.flatMap((qid) => (classesByQual.get(qid) ?? []).flatMap((c) => c.codes)),
    [shownQualIds, classesByQual],
  );

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function runMatch() {
    const wanted = parsePastedCodes(pasted);
    if (!wanted.length) {
      setMatches(null);
      setUnmatched([]);
      return;
    }
    const result = matchQualifications(wanted, codeToQuals, qualNames);
    setMatches(result.matches);
    setUnmatched(result.unmatched);
    // Select exactly the pasted codes that were found.
    const found = new Set(result.matches.flatMap((m) => m.codes));
    setSelected(new Set([...found]));
    if (result.matches.length) setQualId(result.matches[0].qualId);
  }

  function clearMatch() {
    setMatches(null);
    setUnmatched([]);
    setPasted("");
    setSelected(new Set());
  }

  /** Output lines, grouped by qualification when more than one is involved. */
  const outputLines = useMemo(() => {
    const lines: string[] = [];
    const multi = shownQualIds.length > 1;
    for (const qid of shownQualIds) {
      const rows = (classesByQual.get(qid) ?? [])
        .map((c) => ({
          name: c.name,
          picked: c.codes.filter((code) => selected.has(code)),
        }))
        .filter((c) => c.picked.length > 0);
      if (!rows.length) continue;
      if (multi) {
        if (lines.length) lines.push("");
        lines.push(`${qualNames.get(qid) ?? `Qualification #${qid}`}:`);
      }
      for (const r of rows) lines.push(`${r.name} (${r.picked.join(", ")})`);
    }
    return lines;
  }, [shownQualIds, classesByQual, selected, qualNames]);

  async function copyOutput() {
    try {
      const plain = outputLines.join("\n");
      const html = outputLines
        .map((line) =>
          line === ""
            ? "<p style=\"margin:0 0 4px;\">&nbsp;</p>"
            : `<p style="font-family:Arial,sans-serif;font-size:13px;margin:0 0 4px;">${line
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
            value={matches ? "" : (qualId ?? "")}
            disabled={!!matches}
            title={matches ? "Showing the qualifications matched from your pasted list" : undefined}
            onChange={(e) => {
              setQualId(e.target.value === "" ? null : Number(e.target.value));
              setSelected(new Set());
            }}
          >
            {matches && <option value="">(matched from list)</option>}
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

      {!loading && (
        <div className="unit-mapper-paste">
          <label className="unit-mapper-paste-label" htmlFor="unit-mapper-paste-box">
            Paste a list of study units
          </label>
          <p className="muted entity-hint">
            One code per line (or comma separated). The matching qualification is worked out
            from the list as a whole, so a unit shared by two qualifications is placed using
            the rest of the codes as context.
          </p>
          <div className="unit-mapper-paste-row">
            <textarea
              id="unit-mapper-paste-box"
              className="unit-mapper-paste-box"
              rows={6}
              spellCheck={false}
              placeholder={"ICTCLD506\nICTNWK529\nICTNWK536\nICTSAS526"}
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
            />
            <div className="unit-mapper-paste-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={!pasted.trim()}
                onClick={runMatch}
              >
                Match units
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={!pasted && !matches}
                onClick={clearMatch}
              >
                Reset
              </button>
            </div>
          </div>

          {matches && (
            <div className="unit-mapper-match-summary">
              {matches.length === 0 && (
                <span className="unit-mapper-warn">
                  None of those codes matched a qualification in this session.
                </span>
              )}
              {matches.map((m) => (
                <span key={m.qualId} className="unit-mapper-match-chip">
                  {m.name}
                  <span className="muted"> · {m.codes.length} unit{m.codes.length === 1 ? "" : "s"}</span>
                </span>
              ))}
              {!!unmatched.length && (
                <span className="unit-mapper-warn">
                  Not found: {unmatched.join(", ")}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {!loading && !shownQualIds.length && (
        <p className="panel-empty">Pick a qualification or paste a list of units above.</p>
      )}

      {!loading &&
        shownQualIds.map((qid) => {
          const rows = classesByQual.get(qid) ?? [];
          return (
            <div key={qid} className="unit-mapper-qual-block">
              {shownQualIds.length > 1 && (
                <h3 className="unit-mapper-qual-heading">{qualNames.get(qid) ?? `#${qid}`}</h3>
              )}
              {!rows.length && (
                <p className="panel-empty">
                  No classes with study-unit codes are linked to this qualification.
                </p>
              )}
              <div className="unit-mapper-classes">
                {rows.map((c) => (
                  <div key={`${qid}-${c.id}`} className="unit-mapper-class">
                    <span className="unit-mapper-class-name" title={c.name}>
                      {c.name}
                    </span>
                    <div className="unit-mapper-codes">
                      {c.codes.map((code) => (
                        <button
                          key={`${qid}-${c.id}-${code}`}
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
            </div>
          );
        })}

      {!loading && !!shownQualIds.length && (
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
      )}
    </section>
  );
}
