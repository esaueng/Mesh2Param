import { X } from "lucide-react";
import { Modal } from "../components/Modal";
import { WORKSPACE_SHORTCUTS } from "../workspace/shortcuts";

export function ShortcutHelp({ onClose }: { onClose(): void }) {
  return (
    <Modal className="shortcut-backdrop" labelledBy="shortcut-title" onClose={onClose}>
      <section className="shortcut-dialog">
        <header>
          <div><p>Workspace reference</p><h2 id="shortcut-title">Keyboard shortcuts</h2></div>
          <button autoFocus type="button" onClick={onClose} aria-label="Close keyboard shortcuts"><X size={18} /></button>
        </header>
        <dl>
          {WORKSPACE_SHORTCUTS.map((shortcut) => (
            <div key={shortcut.command}><dt>{shortcut.label}</dt><dd><kbd>{shortcut.keys}</kbd></dd></div>
          ))}
        </dl>
        <p className="shortcut-note">Single-key shortcuts can be disabled in workspace settings.</p>
      </section>
    </Modal>
  );
}
