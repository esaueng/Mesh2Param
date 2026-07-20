import { describe, expect, it } from "vitest";
import { shortcutForEvent, WORKSPACE_SHORTCUTS } from "./shortcuts";

function event(key: string, patch: Partial<KeyboardEvent> = {}) {
  return {
    key,
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    ...patch,
  } as KeyboardEvent;
}

describe("workspace shortcuts", () => {
  it("matches modifier and single-key commands from the documented registry", () => {
    expect(shortcutForEvent(event("s", { ctrlKey: true }), false)?.command).toBe("save");
    expect(shortcutForEvent(event("z", { metaKey: true, shiftKey: true }), false)?.command).toBe("redo");
    expect(shortcutForEvent(event("3"), true)).toBeNull();
    expect(shortcutForEvent(event("?", { shiftKey: true }), true)?.command).toBe("show-help");
  });

  it("honors the single-key preference and rejects ambiguous modifiers", () => {
    expect(shortcutForEvent(event("r"), false)).toBeNull();
    expect(shortcutForEvent(event("r", { altKey: true }), true)).toBeNull();
    expect(shortcutForEvent(event("z", { ctrlKey: true, shiftKey: true }), true)?.command).toBe("redo");
  });

  it("has one documented binding for every command", () => {
    expect(new Set(WORKSPACE_SHORTCUTS.map((shortcut) => shortcut.command)).size)
      .toBe(WORKSPACE_SHORTCUTS.length);
  });
});
