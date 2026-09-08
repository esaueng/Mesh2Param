import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Copy, PanelBottomClose, PictureInPicture2, TerminalSquare, Trash2, X } from "lucide-react";
import { debugLog, useDebugLog, type LogEntry, type LogLevel } from "./debugLog";

export const CONSOLE_HEIGHT = { min: 120, max: 640, step: 24 } as const;

export function clampConsoleHeight(height: number): number {
  if (!Number.isFinite(height)) return 220;
  return Math.min(CONSOLE_HEIGHT.max, Math.max(CONSOLE_HEIGHT.min, Math.round(height)));
}

const LEVELS: ReadonlyArray<{ level: LogLevel; label: string }> = [
  { level: "error", label: "Errors" },
  { level: "warn", label: "Warnings" },
  { level: "info", label: "Info" },
  { level: "debug", label: "Debug" },
];

function formatTime(time: number): string {
  const date = new Date(time);
  return `${date.toLocaleTimeString([], { hour12: false })}.${String(time % 1000).padStart(3, "0")}`;
}

export function formatLine(entry: LogEntry): string {
  const base = `${formatTime(entry.time)} ${entry.level.toUpperCase().padEnd(5)} [${entry.source}] ${entry.message}`;
  return entry.detail === undefined ? base : `${base}\n    ${entry.detail.replace(/\n/g, "\n    ")}`;
}

export interface DebugConsoleProps {
  docked: boolean;
  height: number;
  onDockedChange(docked: boolean): void;
  onHeightChange(height: number): void;
  onClose(): void;
}

/**
 * The workspace log. Docked, it is a bottom drawer that takes its own row of
 * the viewport column (the 3D view shrinks above it); floating, it overlays
 * the viewport as before. Severity filters are per level and additive, so
 * "warnings and errors" is the two-chip selection rather than a special mode.
 */
export function DebugConsole({ docked, height, onDockedChange, onHeightChange, onClose }: DebugConsoleProps) {
  const entries = useDebugLog();
  const [enabled, setEnabled] = useState<Record<LogLevel, boolean>>({ error: true, warn: true, info: true, debug: true });
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; startY: number; startHeight: number } | null>(null);

  const counts = useMemo(() => {
    const total: Record<LogLevel, number> = { error: 0, warn: 0, info: 0, debug: 0 };
    for (const entry of entries) total[entry.level] += 1;
    return total;
  }, [entries]);
  const shown = useMemo(() => entries.filter((entry) => enabled[entry.level]), [entries, enabled]);
  const allEnabled = LEVELS.every(({ level }) => enabled[level]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [shown.length]);

  const copyAll = () => {
    void navigator.clipboard?.writeText(shown.map(formatLine).join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    drag.current = { pointerId: event.pointerId, startY: event.clientY, startHeight: height };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (state === null || state.pointerId !== event.pointerId) return;
    // The handle is the drawer's top edge, so dragging up makes it taller.
    onHeightChange(clampConsoleHeight(state.startHeight + (state.startY - event.clientY)));
  };
  const onPointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onHandleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? CONSOLE_HEIGHT.step * 4 : CONSOLE_HEIGHT.step;
    if (event.key === "ArrowUp") onHeightChange(clampConsoleHeight(height + step));
    else if (event.key === "ArrowDown") onHeightChange(clampConsoleHeight(height - step));
    else return;
    event.preventDefault();
  };

  return (
    <section
      className={`debug-console ${docked ? "docked" : "floating"}`}
      aria-label="Debug console"
      data-docked={docked ? "true" : "false"}
    >
      <div
        className="dc-resize"
        role="separator"
        aria-label="Resize console"
        aria-orientation="horizontal"
        aria-valuemin={CONSOLE_HEIGHT.min}
        aria-valuemax={CONSOLE_HEIGHT.max}
        aria-valuenow={height}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onKeyDown={onHandleKey}
      />
      <header className="dc-head">
        <span className="dc-title">
          <TerminalSquare size={14} aria-hidden />
          Console
          <em aria-label={`${shown.length} of ${entries.length} entries shown`}>{shown.length}/{entries.length}</em>
        </span>
        <div className="dc-filters" role="group" aria-label="Severity filter">
          {LEVELS.map(({ level, label }) => (
            <button
              key={level}
              type="button"
              className={`dc-filter lvl-${level} ${enabled[level] ? "active" : ""}`}
              aria-pressed={enabled[level]}
              onClick={() => setEnabled((current) => ({ ...current, [level]: !current[level] }))}
              title={enabled[level] ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            >
              <span className="dc-filter-dot" aria-hidden />
              {label}
              <span className="dc-filter-count">{counts[level]}</span>
            </button>
          ))}
          {allEnabled ? null : (
            <button type="button" className="dc-filter-reset" onClick={() => setEnabled({ error: true, warn: true, info: true, debug: true })}>
              All
            </button>
          )}
        </div>
        <div className="dc-actions">
          <button type="button" onClick={copyAll} title="Copy the shown entries"><Copy size={13} aria-hidden />{copied ? "Copied" : "Copy"}</button>
          <button type="button" onClick={() => debugLog.clear()} title="Clear the log"><Trash2 size={13} aria-hidden />Clear</button>
          <button
            type="button"
            className="dc-icon"
            onClick={() => onDockedChange(!docked)}
            aria-pressed={docked}
            aria-label={docked ? "Float console over the viewport" : "Dock console below the viewport"}
            title={docked ? "Float over the viewport" : "Dock below the viewport"}
          >
            {docked ? <PictureInPicture2 size={14} aria-hidden /> : <PanelBottomClose size={14} aria-hidden />}
          </button>
          <button type="button" className="dc-icon dc-close" onClick={onClose} aria-label="Close console"><X size={15} aria-hidden /></button>
        </div>
      </header>
      <div className="dc-log" ref={scrollRef} role="log" aria-label="Log entries">
        {shown.length === 0 ? (
          <p className="dc-empty">{entries.length === 0 ? "No log entries yet." : "No entries match the severity filter."}</p>
        ) : (
          shown.map((entry) => (
            <div key={entry.id} className={`dc-row lvl-${entry.level}`}>
              <time dateTime={new Date(entry.time).toISOString()}>{formatTime(entry.time)}</time>
              <span className="dc-lvl">{entry.level}</span>
              <span className="dc-src">{entry.source}</span>
              <span className="dc-msg">
                {entry.message}
                {entry.detail === undefined ? null : <pre>{entry.detail}</pre>}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
