import { describe, expect, it } from "vitest";
import {
  edgeOverlayKind,
  displayMaterialProperties,
  patchForFace,
  selectedTriangleRanges,
  usesAnalyticResultShading,
  usesCreasedSurfaceNormals,
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
  it("smooths reconstructed B-Rep tessellation and the source comparison ghost", () => {
    expect(usesAnalyticResultShading("reconstructed")).toBe(true);
    expect(usesAnalyticResultShading("source")).toBe(false);
    expect(usesAnalyticResultShading("patches")).toBe(false);
    expect(usesCreasedSurfaceNormals("reconstructed", false)).toBe(true);
    expect(usesCreasedSurfaceNormals("reconstructed", false, true)).toBe(false);
    expect(usesCreasedSurfaceNormals("source", true)).toBe(true);
    expect(usesCreasedSurfaceNormals("source", false)).toBe(false);
  });
});

describe("shaded edge overlay", () => {
  it("shows feature creases on results without exposing their tessellation triangles", () => {
    expect(edgeOverlayKind("reconstructed", false, true, false)).toBe("creases");
    expect(edgeOverlayKind("source", false, true, false)).toBe("triangles");
    expect(edgeOverlayKind("source", false, true, true)).toBe("none");
    expect(edgeOverlayKind("reconstructed", true, true, false)).toBe("none");
    expect(edgeOverlayKind("reconstructed", false, false, false)).toBe("none");
  });

  it("keeps dense meshes on the lightweight path", () => {
    expect(edgeOverlayKind("source", false, true, false, 45_615)).toBe("none");
    expect(edgeOverlayKind("source", false, true, false, 20_000)).toBe("triangles");
    expect(edgeOverlayKind("reconstructed", false, true, false, 45_615, true)).toBe("none");
  });

  it("draws facet boundaries on sparse faceted result proxies rather than suppressing them", () => {
    expect(edgeOverlayKind("reconstructed", false, true, false, 6_260, true)).toBe("creases");
    expect(edgeOverlayKind("reconstructed", false, true, false, 20_000, true)).toBe("creases");
    expect(edgeOverlayKind("reconstructed", false, true, false, 20_001, true)).toBe("none");
  });
});

describe("display material modes", () => {
  it("uses transparent non-depth-writing material for x-ray mode", () => {
    expect(displayMaterialProperties("xray", 0.9)).toEqual({
      displayedOpacity: 0.28,
      transparent: true,
      depthWrite: false,
      wireframe: false,
    });
  });

  it("preserves solid opacity for shaded analysis modes", () => {
    expect(displayMaterialProperties("normals", 1)).toEqual({
      displayedOpacity: 1,
      transparent: false,
      depthWrite: true,
      wireframe: false,
    });
    expect(displayMaterialProperties("wireframe", 1).wireframe).toBe(true);
  });
});
