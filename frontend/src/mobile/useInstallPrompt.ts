/** Surface an install affordance for the phone viewer.
 *
 * Chromium fires `beforeinstallprompt`, which we capture so the page can offer
 * a real Install button instead of leaving it buried in the browser menu.
 * iOS never fires it — Safari only offers Share → Add to Home Screen — so we
 * detect that case and hand back instructions instead.
 */
import { useEffect, useState } from "react";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export type InstallState = {
  /** A real prompt is available — show a button. */
  canPrompt: boolean;
  /** No prompt exists on this platform; show the manual steps. */
  needsManualSteps: boolean;
  platform: "ios" | "android" | "desktop";
  installed: boolean;
  promptInstall: () => Promise<"accepted" | "dismissed" | "unavailable">;
};

function detectPlatform(): "ios" | "android" | "desktop" {
  const ua = navigator.userAgent;
  // iPadOS 13+ reports as Macintosh, so check for touch as well.
  const iOS =
    /iPhone|iPad|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && typeof document !== "undefined" && "ontouchend" in document);
  if (iOS) return "ios";
  if (/Android/.test(ua)) return "android";
  return "desktop";
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari's own flag, which predates display-mode.
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

export function useInstallPrompt(): InstallState {
  const [deferred, setDeferred] = useState<InstallEvent | null>(null);
  const [installed, setInstalled] = useState(() => isStandalone());
  const platform = detectPlatform();

  useEffect(() => {
    const onPrompt = (e: Event) => {
      // Keep the event so we can trigger it from our own button later.
      e.preventDefault();
      setDeferred(e as InstallEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setDeferred(null);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  return {
    canPrompt: !installed && deferred !== null,
    // iOS can always be added by hand; elsewhere only bother once we know no
    // prompt is coming.
    needsManualSteps: !installed && deferred === null && platform === "ios",
    platform,
    installed,
    async promptInstall() {
      if (!deferred) return "unavailable";
      await deferred.prompt();
      const { outcome } = await deferred.userChoice;
      if (outcome === "accepted") setInstalled(true);
      setDeferred(null);
      return outcome;
    },
  };
}
