import { FormEvent, useState } from "react";

type Props = {
  title: string;
  message?: string;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
  onSubmit: (value: string | null) => void;
  onCancel: () => void;
};

export function PromptDialog({
  title,
  message,
  defaultValue = "",
  placeholder,
  confirmLabel = "OK",
  onSubmit,
  onCancel,
}: Props) {
  const [value, setValue] = useState(defaultValue);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    onSubmit(trimmed || null);
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={onCancel}
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
    >
      <div
        className="modal prompt-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="prompt-dialog-title">{title}</h2>
        </div>
        <form className="modal-form" onSubmit={handleSubmit}>
          {message && <p className="muted">{message}</p>}
          <label>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={placeholder}
              autoFocus
            />
          </label>
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
