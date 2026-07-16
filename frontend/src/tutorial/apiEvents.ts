/** Tiny pub/sub of completed API calls, used by tutorial step verification.
 *
 * apiFetch emits one event per response; the tutorial engine re-runs the
 * current step's verify when a call matching its `watch.api` pattern lands.
 * Never verifies gestures — only the backend state the gesture produced.
 */
export type ApiEvent = {
  path: string;
  method: string;
  ok: boolean;
};

type Listener = (event: ApiEvent) => void;

const listeners = new Set<Listener>();

export function emitApiEvent(event: ApiEvent): void {
  for (const listener of listeners) {
    try {
      listener(event);
    } catch {
      /* a broken listener must never break API calls */
    }
  }
}

export function onApiEvent(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
