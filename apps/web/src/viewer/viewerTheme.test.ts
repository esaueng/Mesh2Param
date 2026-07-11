import { describe, expect, it } from "vitest";
import { surfaceColor, viewerPalette } from "./viewerTheme";

function channel(value: number): number {
  const normalized = value / 255;
  return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const value = Number.parseInt(hex.slice(1), 16);
  return 0.2126 * channel(value >> 16) + 0.7152 * channel((value >> 8) & 255) + 0.0722 * channel(value & 255);
}

function contrast(left: string, right: string): number {
  const values = [luminance(left), luminance(right)].sort((a, b) => b - a);
  return (values[0]! + 0.05) / (values[1]! + 0.05);
}

describe("viewer theme palettes", () => {
  it("keeps neutral geometry distinct from both light and dark canvases", () => {
    for (const theme of ["dark", "light"] as const) {
      const palette = viewerPalette(theme);
      expect(contrast(palette.background, palette.surfaces.reconstructed)).toBeGreaterThan(4.5);
      expect(contrast(palette.background, palette.gridMajor)).toBeGreaterThan(1.8);
    }
  });

  it("preserves residual artifact colors while tinting ordinary and patch layers", () => {
    const palette = viewerPalette("light");
    expect(surfaceColor("source", palette)).toBe(palette.surfaces.source);
    expect(surfaceColor("patches", palette)).toBe(palette.patch);
    expect(surfaceColor("residual", palette)).toBeNull();
  });
});
