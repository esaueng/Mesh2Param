import { describe, expect, it, vi } from "vitest";

import { APP_PREFERENCES_KEY, loadAppPreferences, saveAppPreferences, type AppPreferences } from "./appPreferences";

const preferences: AppPreferences = {
  viewer: {
    mode: "overlay",
    visible: {
      source: true,
      repaired: false,
      analysis: false,
      patches: false,
      reconstructed: true,
      residual: false,
    },
    sourceOpacity: 0.35,
    resultOpacity: 0.8,
    projection: "orthographic",
    shading: "zebra",
    edges: false,
  },
  shell: {
    theme: "light",
    railCollapsed: true,
    inspectorExpanded: false,
    bottomDrawerExpanded: true,
    bottomDrawerHeight: 280,
    singleKeyShortcuts: false,
  },
};

describe("app preference persistence", () => {
  it("round-trips all display and shell preferences through a versioned key", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };

    saveAppPreferences(preferences, storage);

    expect(values.has(APP_PREFERENCES_KEY)).toBe(true);
    expect(loadAppPreferences(storage)).toEqual(preferences);
  });

  it("ignores corrupt or incompatible saved values without breaking startup", () => {
    expect(loadAppPreferences({ getItem: () => "not-json" })).toBeNull();
    expect(loadAppPreferences({ getItem: () => JSON.stringify({ viewer: { mode: "invalid" }, shell: {} }) })).toBeNull();
  });

  it("tolerates storage being unavailable", () => {
    const storage = { setItem: vi.fn(() => { throw new Error("blocked"); }) };
    expect(() => saveAppPreferences(preferences, storage)).not.toThrow();
  });
});
