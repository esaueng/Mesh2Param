import { describe, expect, it } from "vitest";
import {
  patchForFace,
  selectedTriangleRanges,
  usesAnalyticResultShading,
  usesShadedEdgeOverlay,
  type SelectionRange,
} from "./ArtifactLayer";

const ranges: SelectionRange[] = [
  { triangleStart: 0, triangleEndExclusive: 4, patchId: "patch-a", semanticIds: ["patch-a"] },
  { triangleStart: 4, triangleEndExclusive: 8, patchId: "patch-b", semanticIds: ["patch-b"] },
  { triangleStart: 8, triangleEndExclusive: 10, patchId: "patch-a", semanticIds: ["patch-a"] },
];

describe("selection map lookup", () => {
  it("resolves face indices against the authoritative triangle ranges", () => {
    expect(patchForFace(ranges, 0)).toBe("patch-a");
    expect(patchForFace(ranges, 7)).toBe("patch-b");
    expect(patchForFace(ranges, 10)).toBeNull();
  });

  it("retains every disjoint range for the selected viewport highlight", () => {
    expect(selectedTriangleRanges(ranges, "patch-a")).toHaveLength(2);
    expect(selectedTriangleRanges(ranges, null)).toEqual([]);
  });
});

describe("analytic result shading", () => {
  it("smooths only reconstructed B-Rep tessellation while preserving source facets", () => {
    expect(usesAnalyticResultShading("reconstructed")).toBe(true);
    expect(usesAnalyticResultShading("source")).toBe(false);
    expect(usesAnalyticResultShading("patches")).toBe(false);
  });
});

describe("shaded edge overlay", () => {
  it("adds edges over shaded surfaces without duplicating pure wireframe rendering", () => {
    expect(usesShadedEdgeOverlay(false, true)).toBe(true);
    expect(usesShadedEdgeOverlay(true, true)).toBe(false);
    expect(usesShadedEdgeOverlay(false, false)).toBe(false);
  });
});
