import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { WORKSPACE_SHORTCUTS } from "../workspace/shortcuts";

export function ShortcutHelp({ onClose }: { onClose(): void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);

  return (
    <div className="shortcut-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="shortcut-dialog" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
        <header>
          <div><p>Workspace reference</p><h2 id="shortcut-title">Keyboard shortcuts</h2></div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close keyboard shortcuts"><X size={18} /></button>
        </header>
        <dl>
          {WORKSPACE_SHORTCUTS.map((shortcut) => (
            <div key={shortcut.command}><dt>{shortcut.label}</dt><dd><kbd>{shortcut.keys}</kbd></dd></div>
          ))}
        </dl>
        <p className="shortcut-note">Single-key shortcuts can be disabled in workspace settings.</p>
      </section>
    </div>
  );
}
