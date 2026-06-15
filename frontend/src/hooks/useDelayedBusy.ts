import { useCallback, useEffect, useRef, useState } from "react";

/** Show busy UI only after `delayMs` — avoids flashing for fast operations. */
export function useDelayedBusy(delayMs = 5000) {
  const [busy, setBusy] = useState(false);
  const [showBusy, setShowBusy] = useState(false);
  const delayRef = useRef<number | null>(null);

  useEffect(() => {
    if (!busy) {
      setShowBusy(false);
      if (delayRef.current != null) {
        window.clearTimeout(delayRef.current);
        delayRef.current = null;
      }
      return;
    }
    delayRef.current = window.setTimeout(() => setShowBusy(true), delayMs);
    return () => {
      if (delayRef.current != null) {
        window.clearTimeout(delayRef.current);
        delayRef.current = null;
      }
    };
  }, [busy, delayMs]);

  const run = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  }, []);

  return { busy, showBusy, run };
}
