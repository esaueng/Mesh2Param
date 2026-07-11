import { useSyncExternalStore } from "react";

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogEntry {
  id: number;
  time: number;
  level: LogLevel;
  source: string;
  message: string;
  detail?: string;
}

const MAX_ENTRIES = 600;
let entries: LogEntry[] = [];
let seq = 0;
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

function stringifyDetail(detail: unknown): string | undefined {
  if (detail === undefined || detail === null) return undefined;
  if (typeof detail === "string") return detail;
  if (detail instanceof Error) return `${detail.name}: ${detail.message}`;
  try {
    return JSON.stringify(detail, (_key, value) => (value instanceof Error ? `${value.name}: ${value.message}` : value), 2);
  } catch {
    return String(detail);
  }
}

function push(level: LogLevel, source: string, message: string, detail?: unknown): void {
  seq += 1;
  const encoded = stringifyDetail(detail);
  const entry: LogEntry = { id: seq, time: Date.now(), level, source, message, ...(encoded === undefined ? {} : { detail: encoded }) };
  entries = entries.length >= MAX_ENTRIES ? [...entries.slice(entries.length - MAX_ENTRIES + 1), entry] : [...entries, entry];
  notify();
  // Mirror to the browser console so failures are visible in devtools too.
  const sink = level === "error" ? console.error : level === "warn" ? console.warn : level === "debug" ? console.debug : console.info;
  sink(`[m2p:${source}] ${message}`, detail ?? "");
}

export const debugLog = {
  debug: (source: string, message: string, detail?: unknown) => push("debug", source, message, detail),
  info: (source: string, message: string, detail?: unknown) => push("info", source, message, detail),
  warn: (source: string, message: string, detail?: unknown) => push("warn", source, message, detail),
  error: (source: string, message: string, detail?: unknown) => push("error", source, message, detail),
  clear: () => { entries = []; notify(); },
  snapshot: (): LogEntry[] => entries,
  subscribe: (listener: () => void): (() => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useDebugLog(): LogEntry[] {
  return useSyncExternalStore(debugLog.subscribe, debugLog.snapshot, debugLog.snapshot);
}
