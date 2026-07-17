import type { PersistedProjectUI, ViewerLayer, ViewerPreferences } from "../state/types";

export const APP_PREFERENCES_KEY = "mesh2param-app-preferences:v1";

export type PersistedShellPreferences = PersistedProjectUI["shell"];

export interface AppPreferences {
  viewer: ViewerPreferences;
  shell: PersistedShellPreferences;
}

const VIEWER_LAYERS: ViewerLayer[] = [
  "source",
  "repaired",
  "analysis",
  "patches",
  "reconstructed",
  "residual",
];

export function loadAppPreferences(storage: Pick<Storage, "getItem"> | null = browserStorage()): AppPreferences | null {
  if (storage === null) return null;
  try {
    const serialized = storage.getItem(APP_PREFERENCES_KEY);
    if (serialized === null) return null;
    const value: unknown = JSON.parse(serialized);
    return isAppPreferences(value) ? value : null;
  } catch {
    return null;
  }
}

export function saveAppPreferences(
  preferences: AppPreferences,
  storage: Pick<Storage, "setItem"> | null = browserStorage(),
): void {
  if (storage === null) return;
  try {
    storage.setItem(APP_PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // Preference persistence is best-effort in private or storage-disabled contexts.
  }
}

export function persistedShellPreferences(shell: PersistedProjectUI["shell"]): PersistedShellPreferences {
  return {
    theme: shell.theme,
    railCollapsed: shell.railCollapsed,
    inspectorExpanded: shell.inspectorExpanded,
    bottomDrawerExpanded: shell.bottomDrawerExpanded,
    bottomDrawerHeight: shell.bottomDrawerHeight,
    singleKeyShortcuts: shell.singleKeyShortcuts,
  };
}

function browserStorage(): Storage | null {
  return typeof localStorage === "undefined" ? null : localStorage;
}

function isAppPreferences(value: unknown): value is AppPreferences {
  if (!isRecord(value) || !isRecord(value.viewer) || !isRecord(value.shell)) return false;
  const { viewer, shell } = value;
  if (![
    "source", "repaired", "analysis", "patches", "reconstructed", "residual", "overlay",
  ].includes(String(viewer.mode))) return false;
  if (!["perspective", "orthographic"].includes(String(viewer.projection))) return false;
  if (!["shaded", "wireframe", "xray", "normals", "zebra"].includes(String(viewer.shading))) return false;
  const visible = viewer.visible;
  if (!isRecord(visible) || !VIEWER_LAYERS.every((layer) => typeof visible[layer] === "boolean")) return false;
  if (!isUnitInterval(viewer.sourceOpacity) || !isUnitInterval(viewer.resultOpacity) || typeof viewer.edges !== "boolean") return false;
  return ["dark", "light"].includes(String(shell.theme))
    && typeof shell.railCollapsed === "boolean"
    && typeof shell.inspectorExpanded === "boolean"
    && typeof shell.bottomDrawerExpanded === "boolean"
    && typeof shell.bottomDrawerHeight === "number"
    && Number.isFinite(shell.bottomDrawerHeight)
    && typeof shell.singleKeyShortcuts === "boolean";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUnitInterval(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}
