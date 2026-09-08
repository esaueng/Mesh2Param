import { useSyncExternalStore } from "react";

/**
 * Persisted layout of the command panel: its width, which sections are
 * collapsed, and whether the console is docked into the viewport column or
 * floats over it. Kept out of the workspace store on purpose: this is pure
 * chrome state that never travels with a project.
 */

export const PANEL_LAYOUT_KEY = "mesh2param-panel-layout:v1";

export const PANEL_SECTION_IDS = ["file", "view", "analysis", "patches", "convert"] as const;
export type PanelSectionId = (typeof PANEL_SECTION_IDS)[number];

export const PANEL_WIDTH = { min: 220, max: 440, default: 248, step: 16 } as const;

export interface PanelLayout {
  width: number;
  collapsed: Record<PanelSectionId, boolean>;
  consoleDocked: boolean;
  /** Reference grid under the model. Viewer chrome, so it lives here and not in the project file. */
  grid: boolean;
}

export const defaultPanelLayout: PanelLayout = {
  width: PANEL_WIDTH.default,
  collapsed: { file: false, view: false, analysis: false, patches: false, convert: false },
  consoleDocked: true,
  grid: false,
};

export function clampPanelWidth(width: number): number {
  if (!Number.isFinite(width)) return PANEL_WIDTH.default;
  return Math.min(PANEL_WIDTH.max, Math.max(PANEL_WIDTH.min, Math.round(width)));
}

export function loadPanelLayout(storage: Pick<Storage, "getItem"> | null = browserStorage()): PanelLayout {
  if (storage === null) return defaultPanelLayout;
  try {
    const serialized = storage.getItem(PANEL_LAYOUT_KEY);
    if (serialized === null) return defaultPanelLayout;
    return normalize(JSON.parse(serialized));
  } catch {
    return defaultPanelLayout;
  }
}

export function savePanelLayout(layout: PanelLayout, storage: Pick<Storage, "setItem"> | null = browserStorage()): void {
  if (storage === null) return;
  try {
    storage.setItem(PANEL_LAYOUT_KEY, JSON.stringify(layout));
  } catch {
    // Layout persistence is best-effort in private or storage-disabled contexts.
  }
}

/** Accepts partial or malformed stored values and fills in the defaults. */
function normalize(value: unknown): PanelLayout {
  if (!isRecord(value)) return defaultPanelLayout;
  const collapsed = { ...defaultPanelLayout.collapsed };
  if (isRecord(value.collapsed)) {
    for (const id of PANEL_SECTION_IDS) {
      if (typeof value.collapsed[id] === "boolean") collapsed[id] = value.collapsed[id];
    }
  }
  return {
    width: typeof value.width === "number" ? clampPanelWidth(value.width) : PANEL_WIDTH.default,
    collapsed,
    consoleDocked: typeof value.consoleDocked === "boolean" ? value.consoleDocked : defaultPanelLayout.consoleDocked,
    grid: typeof value.grid === "boolean" ? value.grid : defaultPanelLayout.grid,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function browserStorage(): Storage | null {
  return typeof localStorage === "undefined" ? null : localStorage;
}

// ---- module store -------------------------------------------------------

let layout: PanelLayout = loadPanelLayout();
const listeners = new Set<() => void>();

function commit(next: PanelLayout): void {
  layout = next;
  savePanelLayout(next);
  for (const listener of listeners) listener();
}

export const panelLayoutStore = {
  snapshot: (): PanelLayout => layout,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  setWidth(width: number): void {
    const next = clampPanelWidth(width);
    if (next !== layout.width) commit({ ...layout, width: next });
  },
  resetWidth(): void {
    panelLayoutStore.setWidth(PANEL_WIDTH.default);
  },
  setCollapsed(id: PanelSectionId, collapsed: boolean): void {
    if (layout.collapsed[id] === collapsed) return;
    commit({ ...layout, collapsed: { ...layout.collapsed, [id]: collapsed } });
  },
  toggleCollapsed(id: PanelSectionId): void {
    panelLayoutStore.setCollapsed(id, !layout.collapsed[id]);
  },
  setConsoleDocked(docked: boolean): void {
    if (layout.consoleDocked !== docked) commit({ ...layout, consoleDocked: docked });
  },
  setGrid(grid: boolean): void {
    if (layout.grid !== grid) commit({ ...layout, grid });
  },
  /** Test hook: drop the in-memory state and reread storage. */
  reload(): void {
    commit(loadPanelLayout());
  },
};

export function usePanelLayout(): PanelLayout {
  return useSyncExternalStore(panelLayoutStore.subscribe, panelLayoutStore.snapshot, panelLayoutStore.snapshot);
}
