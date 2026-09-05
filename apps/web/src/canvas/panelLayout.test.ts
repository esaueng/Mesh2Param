import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clampPanelWidth,
  defaultPanelLayout,
  loadPanelLayout,
  PANEL_LAYOUT_KEY,
  PANEL_WIDTH,
  panelLayoutStore,
  savePanelLayout,
} from "./panelLayout";

class MemoryStorage {
  private readonly items = new Map<string, string>();
  getItem(key: string): string | null { return this.items.get(key) ?? null; }
  setItem(key: string, value: string): void { this.items.set(key, value); }
}

describe("panel layout persistence", () => {
  it("round-trips a layout", () => {
    const storage = new MemoryStorage();
    const layout = { ...defaultPanelLayout, width: 300, collapsed: { ...defaultPanelLayout.collapsed, view: true }, consoleDocked: false };
    savePanelLayout(layout, storage);
    expect(loadPanelLayout(storage)).toEqual(layout);
  });

  it("falls back to the defaults for missing, malformed, or partial values", () => {
    const storage = new MemoryStorage();
    expect(loadPanelLayout(storage)).toEqual(defaultPanelLayout);
    storage.setItem(PANEL_LAYOUT_KEY, "{not json");
    expect(loadPanelLayout(storage)).toEqual(defaultPanelLayout);
    storage.setItem(PANEL_LAYOUT_KEY, JSON.stringify({ width: "wide", collapsed: { file: true, bogus: true }, consoleDocked: "yes" }));
    expect(loadPanelLayout(storage)).toEqual({
      ...defaultPanelLayout,
      collapsed: { ...defaultPanelLayout.collapsed, file: true },
    });
    expect(loadPanelLayout(null)).toEqual(defaultPanelLayout);
  });

  it("clamps the width to the allowed range", () => {
    expect(clampPanelWidth(10)).toBe(PANEL_WIDTH.min);
    expect(clampPanelWidth(10_000)).toBe(PANEL_WIDTH.max);
    expect(clampPanelWidth(300.4)).toBe(300);
    expect(clampPanelWidth(Number.NaN)).toBe(PANEL_WIDTH.default);
    const storage = new MemoryStorage();
    storage.setItem(PANEL_LAYOUT_KEY, JSON.stringify({ width: 9_999 }));
    expect(loadPanelLayout(storage).width).toBe(PANEL_WIDTH.max);
  });
});

describe("panelLayoutStore", () => {
  beforeEach(() => {
    localStorage.removeItem(PANEL_LAYOUT_KEY);
    panelLayoutStore.reload();
  });
  afterEach(() => {
    localStorage.removeItem(PANEL_LAYOUT_KEY);
    panelLayoutStore.reload();
  });

  it("persists every change and notifies subscribers", () => {
    let notified = 0;
    const unsubscribe = panelLayoutStore.subscribe(() => { notified += 1; });

    panelLayoutStore.setWidth(320);
    panelLayoutStore.toggleCollapsed("patches");
    panelLayoutStore.setConsoleDocked(false);
    unsubscribe();

    expect(notified).toBe(3);
    expect(panelLayoutStore.snapshot()).toEqual({
      width: 320,
      collapsed: { ...defaultPanelLayout.collapsed, patches: true },
      consoleDocked: false,
    });
    expect(loadPanelLayout(localStorage)).toEqual(panelLayoutStore.snapshot());
  });

  it("ignores no-op writes so subscribers do not re-render", () => {
    let notified = 0;
    const unsubscribe = panelLayoutStore.subscribe(() => { notified += 1; });
    panelLayoutStore.setWidth(PANEL_WIDTH.default);
    panelLayoutStore.setCollapsed("file", false);
    panelLayoutStore.setConsoleDocked(true);
    unsubscribe();
    expect(notified).toBe(0);
  });

  it("resets the width to the default", () => {
    panelLayoutStore.setWidth(PANEL_WIDTH.max);
    panelLayoutStore.resetWidth();
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default);
  });
});
