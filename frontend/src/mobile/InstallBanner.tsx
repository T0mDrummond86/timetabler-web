/** Offers installation from inside the phone viewer, because neither platform
 *  makes it obvious: Chromium hides it in the ⋮ menu, and iOS never prompts. */
import { useState } from "react";
import { useInstallPrompt } from "./useInstallPrompt";

const DISMISS_KEY = "tafetabler-install-dismissed";

export function InstallBanner() {
  const install = useInstallPrompt();
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === "1",
  );

  if (install.installed) return null;
  if (!install.canPrompt && !install.needsManualSteps) return null;
  if (dismissed) return null;

  function close() {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  return (
    <div className="mv-install" role="region" aria-label="Install this app">
      <span className="mv-install-text">
        {install.canPrompt ? (
          <>Add TAFEtabler to your home screen for full-screen, offline access.</>
        ) : (
          <>
            To install: tap <strong>Share</strong> <span aria-hidden>⬆︎</span> in Safari,
            then <strong>Add to Home Screen</strong>.
          </>
        )}
      </span>
      {install.canPrompt && (
        <button
          type="button"
          className="mv-install-btn"
          onClick={() => void install.promptInstall()}
        >
          Install
        </button>
      )}
      <button type="button" className="mv-install-close" aria-label="Dismiss" onClick={close}>
        ×
      </button>
    </div>
  );
}
