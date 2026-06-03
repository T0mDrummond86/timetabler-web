import { useEffect, useMemo, useState } from "react";

export type ImportPickerItem = {
  id: number;
  name: string;
  already_in_target: boolean;
  linked_classes?: string[];
};

type Props = {
  title: string;
  description: string;
  items: ImportPickerItem[];
  loading?: boolean;
  onClose: () => void;
  onConfirm: (selectedIds: number[]) => void;
};

export function LinkedImportPickerModal({
  title,
  description,
  items,
  loading = false,
  onClose,
  onConfirm,
}: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");

  const importable = useMemo(
    () => items.filter((i) => !i.already_in_target),
    [items],
  );

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return importable;
    return importable.filter((i) => i.name.toLowerCase().includes(q));
  }, [importable, filter]);

  useEffect(() => {
    setSelected(new Set());
    setFilter("");
  }, [items]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllVisible() {
    setSelected(new Set(filtered.map((i) => i.id)));
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal card linked-import-picker-modal"
        role="dialog"
        aria-modal
        aria-labelledby="linked-import-picker-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="linked-import-picker-title">{title}</h2>
          <button type="button" className="btn-secondary btn-xs" onClick={onClose}>
            Close
          </button>
        </header>
        <p className="modal-lead">{description}</p>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <div className="linked-import-picker-toolbar">
              <input
                type="search"
                className="field-input"
                placeholder="Filter…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <button type="button" className="btn-secondary btn-xs" onClick={selectAllVisible}>
                Select all shown
              </button>
              <button type="button" className="btn-secondary btn-xs" onClick={() => setSelected(new Set())}>
                Clear
              </button>
            </div>
            <ul className="linked-import-picker-list">
              {filtered.map((item) => (
                <li key={item.id}>
                  <label className="linked-import-picker-row">
                    <input
                      type="checkbox"
                      checked={selected.has(item.id)}
                      onChange={() => toggle(item.id)}
                    />
                    <span className="linked-import-picker-label">
                      <strong>{item.name}</strong>
                      {item.linked_classes && item.linked_classes.length > 0 && (
                        <span className="muted linked-import-picker-meta">
                          Classes: {item.linked_classes.join(", ")}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              ))}
              {!filtered.length && (
                <li className="muted linked-import-picker-empty">
                  {importable.length
                    ? "No matches for your filter."
                    : "Nothing available to import (all already exist in the target session)."}
                </li>
              )}
            </ul>
            {items.some((i) => i.already_in_target) && (
              <p className="muted entity-hint">
                Items already in the target session are hidden from this list.
              </p>
            )}
          </>
        )}
        <footer className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <span className="modal-footer-spacer" />
          <button
            type="button"
            className="btn-primary"
            disabled={loading || selected.size === 0}
            onClick={() => onConfirm([...selected])}
          >
            Use selection {selected.size > 0 ? `(${selected.size})` : ""}
          </button>
        </footer>
      </div>
    </div>
  );
}
