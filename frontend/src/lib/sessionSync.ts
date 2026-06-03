/**
 * Notify other browser tabs when timetable data changes in this session.
 * Uses BroadcastChannel with a localStorage fallback for older browsers.
 */
import { useEffect, useRef } from "react";

const CHANNEL_NAME = "timetabler-session-sync";
const TAB_ID_KEY = "timetabler-tab-id";
const STORAGE_KEY = "timetabler-session-sync-ping";

export type SessionSyncMessage = {
  sessionId: number;
  sourceTabId: string;
  at: number;
};

function tabId(): string {
  try {
    let id = sessionStorage.getItem(TAB_ID_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(TAB_ID_KEY, id);
    }
    return id;
  } catch {
    return "ephemeral";
  }
}

function postMessage(msg: SessionSyncMessage): void {
  try {
    const channel = new BroadcastChannel(CHANNEL_NAME);
    channel.postMessage(msg);
    channel.close();
  } catch {
    /* BroadcastChannel unavailable */
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msg));
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / quota */
  }
}

function watchSessionIds(sessionId: number, linkedSessionIds?: number[]): Set<number> {
  const ids = new Set<number>([sessionId]);
  for (const id of linkedSessionIds ?? []) {
    if (id) ids.add(id);
  }
  return ids;
}

/** Call after a successful booking or session mutation in this tab. */
export function notifySessionChanged(sessionId: number, linkedSessionIds?: number[]): void {
  if (!sessionId) return;
  const msg = { sourceTabId: tabId(), at: Date.now() };
  for (const id of watchSessionIds(sessionId, linkedSessionIds)) {
    postMessage({ ...msg, sessionId: id });
  }
}

function isRemoteMessage(msg: unknown, watchIds: Set<number>): msg is SessionSyncMessage {
  if (!msg || typeof msg !== "object") return false;
  const m = msg as SessionSyncMessage;
  return watchIds.has(m.sessionId) && m.sourceTabId !== tabId();
}

/** Subscribe to timetable changes made in other tabs for this session and linked peers. */
export function subscribeSessionChanges(
  sessionId: number,
  onRemoteChange: () => void,
  linkedSessionIds?: number[],
): () => void {
  if (!sessionId) return () => undefined;

  const watchIds = watchSessionIds(sessionId, linkedSessionIds);

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  const schedule = () => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      onRemoteChange();
    }, 120);
  };

  const handle = (data: unknown) => {
    if (isRemoteMessage(data, watchIds)) schedule();
  };

  let channel: BroadcastChannel | null = null;
  try {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event: MessageEvent) => handle(event.data);
  } catch {
    channel = null;
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY || !event.newValue) return;
    try {
      handle(JSON.parse(event.newValue) as SessionSyncMessage);
    } catch {
      /* ignore */
    }
  };
  window.addEventListener("storage", onStorage);

  return () => {
    if (debounceTimer) clearTimeout(debounceTimer);
    channel?.close();
    window.removeEventListener("storage", onStorage);
  };
}

export function useSessionSync(
  sessionId: number,
  onRemoteChange: () => void,
  linkedSessionIds?: number[],
): void {
  const handlerRef = useRef(onRemoteChange);
  handlerRef.current = onRemoteChange;
  const linkedKey = linkedSessionIds?.slice().sort((a, b) => a - b).join(",") ?? "";
  useEffect(() => {
    if (!sessionId) return;
    const linked = linkedKey ? linkedKey.split(",").map((s) => Number(s)) : undefined;
    return subscribeSessionChanges(sessionId, () => handlerRef.current(), linked);
  }, [sessionId, linkedKey]);
}
