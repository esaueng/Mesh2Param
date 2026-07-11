import { useEffect, useMemo, useRef, useState } from "react";
import { Copy, TerminalSquare, Trash2, X } from "lucide-react";
import { debugLog, useDebugLog, type LogEntry } from "./debugLog";

function formatTime(time: number): string {
  const date = new Date(time);
  return `${date.toLocaleTimeString([], { hour12: false })}.${String(time % 1000).padStart(3, "0")}`;
}

function formatLine(entry: LogEntry): string {
  const base = `${formatTime(entry.time)} ${entry.level.toUpperCase().padEnd(5)} [${entry.source}] ${entry.message}`;
  return entry.detail === undefined ? base : `${base}\n    ${entry.detail.replace(/\n/g, "\n    ")}`;
}

export function DebugConsole({ onClose }: { onClose(): void }) {
  const entries = useDebugLog();
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const shown = useMemo(
    () => (errorsOnly ? entries.filter((entry) => entry.level === "error" || entry.level === "warn") : entries),
    [entries, errorsOnly],
  );

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [shown.length]);

  const copyAll = () => {
    void navigator.clipboard?.writeText(entries.map(formatLine).join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <section className="debug-console" aria-label="Debug console">
      <header className="dc-head">
        <span className="dc-title"><TerminalSquare size={14} /> Console <em>{entries.length}</em></span>
        <div className="dc-actions">
          <button className={errorsOnly ? "active" : ""} aria-pressed={errorsOnly} onClick={() => setErrorsOnly((value) => !value)}>
            Issues only
          </button>
          <button onClick={copyAll}><Copy size={13} />{copied ? "Copied" : "Copy"}</button>
          <button onClick={() => debugLog.clear()}><Trash2 size={13} />Clear</button>
          <button className="dc-close" onClick={onClose} aria-label="Close console"><X size={15} /></button>
        </div>
      </header>
      <div className="dc-log" ref={scrollRef}>
        {shown.length === 0 ? (
          <p className="dc-empty">{errorsOnly ? "No warnings or errors." : "No log entries yet."}</p>
        ) : (
          shown.map((entry) => (
            <div key={entry.id} className={`dc-row lvl-${entry.level}`}>
              <time>{formatTime(entry.time)}</time>
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
