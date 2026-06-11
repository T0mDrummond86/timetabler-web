import { useState } from "react";
import { createPortal } from "react-dom";
import { CLASS_COLOUR_PRESETS, normalizeHexColour } from "../lib/classColourPresets";

type Props = {
  className?: string | null;
  currentFill?: string | null;
  onApply: (fill: string) => void;
  onReset?: () => void;
  onClose: () => void;
};

export function ClassColourDialog({
  className,
  currentFill,
  onApply,
  onReset,
  onClose,
}: Props) {
  const [customHex, setCustomHex] = useState(currentFill ?? "");
  const [customHexError, setCustomHexError] = useState<string | null>(null);

  function applyCustomHex(e: React.FormEvent) {
    e.preventDefault();
    const normalized = normalizeHexColour(customHex);
    if (!normalized) {
      setCustomHexError("Enter a 6-digit hex colour, e.g. #AABBCC");
      return;
    }
    onApply(normalized);
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="class-colour-dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="class-colour-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="class-colour-dialog-header">
          <h2 id="class-colour-dialog-title">Class colour</h2>
          {className && <p className="muted">{className}</p>}
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="ctx-colour-palette class-colour-dialog-palette">
          {CLASS_COLOUR_PRESETS.map((fill) => (
            <button
              key={fill}
              type="button"
              className="ctx-colour-preset"
              style={{ backgroundColor: fill }}
              title={fill}
              aria-label={`Set class colour ${fill}`}
              onClick={() => onApply(fill)}
            />
          ))}
        </div>
        <form className="ctx-colour-custom class-colour-dialog-custom" onSubmit={applyCustomHex}>
          <label className="ctx-colour-custom-label">
            Custom hex
            <input
              type="text"
              className="ctx-colour-custom-input"
              placeholder="#RRGGBB"
              value={customHex}
              onChange={(e) => {
                setCustomHex(e.target.value);
                setCustomHexError(null);
              }}
              spellCheck={false}
            />
          </label>
          <button type="submit" className="btn-primary btn-xs">
            Apply
          </button>
        </form>
        {customHexError && <p className="error class-colour-dialog-error">{customHexError}</p>}
        <div className="class-colour-dialog-actions">
          {currentFill && onReset && (
            <button type="button" className="btn-secondary" onClick={onReset}>
              Reset to automatic
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
