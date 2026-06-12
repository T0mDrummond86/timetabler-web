import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ClashCheckSetting } from "../types";

const CATEGORY_LABELS: Record<string, string> = {
  clashes: "Double-booking & clashes",
  staff: "Staff rules",
  rooms: "Room rules",
  qualification: "Qualification",
  scheduling: "Scheduling rules",
};

const CATEGORY_ORDER = ["clashes", "staff", "rooms", "qualification", "scheduling"];

type Props = {
  sessionId: number;
  onUpdated?: () => void;
};

export function ClashSettingsPanel({ sessionId, onUpdated }: Props) {
  const [rows, setRows] = useState<ClashCheckSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await api.clashSettings(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load clash settings");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(() => {
    const map = new Map<string, ClashCheckSetting[]>();
    for (const row of rows) {
      const list = map.get(row.category) ?? [];
      list.push(row);
      map.set(row.category, list);
    }
    return CATEGORY_ORDER.filter((c) => map.has(c)).map((category) => ({
      category,
      label: CATEGORY_LABELS[category] ?? category,
      items: map.get(category) ?? [],
    }));
  }, [rows]);

  const enabledCount = rows.filter((r) => r.enabled).length;

  async function onToggle(code: string, enabled: boolean) {
    setSaving(true);
    setError(null);
    setRows((prev) => prev.map((r) => (r.code === code ? { ...r, enabled } : r)));
    try {
      const updated = await api.patchClashSettings(sessionId, { [code]: enabled });
      setRows(updated);
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
      void load();
    } finally {
      setSaving(false);
    }
  }

  async function onReset() {
    setSaving(true);
    setError(null);
    try {
      setRows(await api.resetClashSettings(sessionId));
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset");
    } finally {
      setSaving(false);
    }
  }

  async function setAll(enabled: boolean) {
    setSaving(true);
    setError(null);
    const patch = Object.fromEntries(rows.map((r) => [r.code, enabled]));
    try {
      setRows(await api.patchClashSettings(sessionId, patch));
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
      void load();
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="card clash-settings-panel">
        <p className="muted">Loading clash settings…</p>
      </section>
    );
  }

  return (
    <section className="card clash-settings-panel">
      <div className="clash-settings-head">
        <div>
          <h2>Clash &amp; constraint checks</h2>
          <p className="muted clash-settings-intro">
            Choose which warnings appear on the timetable grid and in the Warnings report.
            Disabled checks are skipped when clash detection runs (including manual &quot;Check
            clashes&quot;).
          </p>
        </div>
        <div className="clash-settings-actions">
          <span className="muted clash-settings-count">
            {enabledCount} of {rows.length} enabled
          </span>
          <button type="button" className="btn-secondary btn-xs" disabled={saving} onClick={() => void setAll(true)}>
            Enable all
          </button>
          <button type="button" className="btn-secondary btn-xs" disabled={saving} onClick={() => void setAll(false)}>
            Disable all
          </button>
          <button type="button" className="btn-secondary btn-xs" disabled={saving} onClick={() => void onReset()}>
            Reset defaults
          </button>
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}

      <div className="clash-settings-groups">
        {grouped.map((group) => (
          <fieldset key={group.category} className="clash-settings-group">
            <legend>{group.label}</legend>
            <ul className="clash-settings-list">
              {group.items.map((item) => (
                <li key={item.code} className="clash-settings-row">
                  <label className="clash-settings-toggle">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      disabled={saving}
                      onChange={(e) => void onToggle(item.code, e.target.checked)}
                    />
                    <span className="clash-settings-label">
                      <span className="clash-settings-name">{item.label}</span>
                      <span
                        className={`clash-settings-severity clash-settings-severity--${item.severity}`}
                      >
                        {item.severity}
                      </span>
                    </span>
                  </label>
                  <p className="clash-settings-desc muted">{item.description}</p>
                </li>
              ))}
            </ul>
          </fieldset>
        ))}
      </div>
    </section>
  );
}
