import type { ShellState, ViewerMode } from "../state/types";

export type ViewerTheme = ShellState["theme"];

export interface ViewerPalette {
  background: string;
  gridMajor: string;
  gridMinor: string;
  patch: string;
  highlight: string;
  highlightEmissive: string;
  highlightEmissiveIntensity: number;
  ambientIntensity: number;
  keyIntensity: number;
  fillIntensity: number;
  surfaces: Record<Exclude<ViewerMode, "overlay" | "patches" | "residual">, string>;
}

const PALETTES: Record<ViewerTheme, ViewerPalette> = {
  dark: {
    background: "#070b10",
    gridMajor: "#1d4a73",
    gridMinor: "#132e49",
    patch: "#4da3ff",
    highlight: "#9dd7ff",
    highlightEmissive: "#0a78d4",
    highlightEmissiveIntensity: 1.35,
    ambientIntensity: 1.1,
    keyIntensity: 2.2,
    fillIntensity: 0.8,
    surfaces: {
      source: "#9fb5c8",
      repaired: "#a9bbb2",
      analysis: "#9fb1c0",
      reconstructed: "#c0c7ce",
    },
  },
  light: {
    background: "#f7f9fc",
    gridMajor: "#8fa5b8",
    gridMinor: "#cbd6e0",
    patch: "#0b63b6",
    highlight: "#07599f",
    highlightEmissive: "#063b69",
    highlightEmissiveIntensity: 0.55,
    ambientIntensity: 0.72,
    keyIntensity: 1.45,
    fillIntensity: 0.45,
    surfaces: {
      source: "#4e6d86",
      repaired: "#506f62",
      analysis: "#536f83",
      reconstructed: "#596a79",
    },
  },
};

export function viewerPalette(theme: ViewerTheme): ViewerPalette {
  return PALETTES[theme];
}

export function surfaceColor(mode: string, palette: ViewerPalette): string | null {
  if (mode === "patches") return palette.patch;
  if (mode === "residual") return null;
  if (mode === "source" || mode === "repaired" || mode === "analysis" || mode === "reconstructed") {
    return palette.surfaces[mode];
  }
  return palette.surfaces.reconstructed;
}
