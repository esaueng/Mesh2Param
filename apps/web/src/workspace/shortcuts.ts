export type ShortcutCommand =
  | "save" | "undo" | "redo" | "fit-view" | "analyze" | "reconstruct"
  | "clear-selection" | "show-help";

export interface WorkspaceShortcut {
  command: ShortcutCommand;
  keys: string;
  label: string;
  key: string;
  modifier?: boolean;
  shift?: boolean;
  singleKey?: boolean;
}

export const WORKSPACE_SHORTCUTS: readonly WorkspaceShortcut[] = [
  { command: "save", keys: "Ctrl/Cmd S", label: "Save project", key: "s", modifier: true },
  { command: "undo", keys: "Ctrl/Cmd Z", label: "Undo", key: "z", modifier: true },
  { command: "redo", keys: "Ctrl/Cmd Shift Z", label: "Redo", key: "z", modifier: true, shift: true },
  { command: "fit-view", keys: "H", label: "Fit model to view", key: "h", singleKey: true },
  { command: "analyze", keys: "A", label: "Analyze source", key: "a", singleKey: true },
  { command: "reconstruct", keys: "R", label: "Reconstruct model", key: "r", singleKey: true },
  { command: "show-help", keys: "?", label: "Show keyboard shortcuts", key: "?", singleKey: true, shift: true },
  { command: "clear-selection", keys: "Esc", label: "Clear selection or close dialog", key: "escape", singleKey: true },
];

export function shortcutForEvent(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey">,
  singleKeyShortcuts: boolean,
): WorkspaceShortcut | null {
  const modifier = event.metaKey || event.ctrlKey;
  const key = event.key.toLowerCase();
  return WORKSPACE_SHORTCUTS.find((shortcut) => (
    shortcut.key === key
    && Boolean(shortcut.modifier) === modifier
    && Boolean(shortcut.shift) === event.shiftKey
    && !event.altKey
    && (!shortcut.singleKey || singleKeyShortcuts)
  )) ?? null;
}
