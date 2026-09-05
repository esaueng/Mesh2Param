import type { ShellState, ViewerMode } from "../state/types";

export type ViewerTheme = ShellState["theme"];

export interface GizmoPalette {
  body: string;
  face: string;
  faceHover: string;
  edge: string;
  label: string;
  labelHover: string;
  corner: string;
  cornerHover: string;
  home: string;
  outline: string;
}

export interface ViewerPalette {
  background: string;
  gridMajor: string;
  gridMinor: string;
  edge: string;
  edgeOpacity: number;
  /** Screen-space edge thickness in CSS pixels; needs a fat-line material to exceed 1. */
  edgeWidth: number;
  patch: string;
  highlight: string;
  highlightEmissive: string;
  highlightEmissiveIntensity: number;
  /** Patch under the pointer (or the panel row under the pointer). */
  hover: string;
  hoverOpacity: number;
  /** Boundary of the selected patch, drawn through the surface. */
  outline: string;
  outlineWidth: number;
  gridOpacity: number;
  gizmo: GizmoPalette;
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
    edge: "#05080b",
    edgeOpacity: 0.72,
    edgeWidth: 1.6,
    patch: "#4da3ff",
    highlight: "#9dd7ff",
    highlightEmissive: "#0a78d4",
    highlightEmissiveIntensity: 1.35,
    hover: "#7fc4ff",
    hoverOpacity: 0.38,
    outline: "#e8f4ff",
    outlineWidth: 2.2,
    gridOpacity: 0.7,
    gizmo: {
      body: "#1d2b3d",
      face: "#31516b",
      faceHover: "#6da4c9",
      edge: "#8fb4d8",
      label: "#e4eef8",
      labelHover: "#ffffff",
      corner: "#a9c9e8",
      cornerHover: "#f8fbff",
      home: "#d9e8f6",
      outline: "#07111d",
    },
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
    edge: "#111820",
    edgeOpacity: 0.62,
    edgeWidth: 1.6,
    patch: "#0b63b6",
    highlight: "#07599f",
    highlightEmissive: "#063b69",
    highlightEmissiveIntensity: 0.55,
    hover: "#2f7fc4",
    hoverOpacity: 0.3,
    outline: "#0b3d6b",
    outlineWidth: 2.2,
    gridOpacity: 0.7,
    gizmo: {
      body: "#dfe7f0",
      face: "#b7c8d8",
      faceHover: "#7fa6c8",
      edge: "#4f6a84",
      label: "#0f1a26",
      labelHover: "#000000",
      corner: "#2f5f8a",
      cornerHover: "#0b63b6",
      home: "#2f5f8a",
      outline: "#f7f9fc",
    },
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
