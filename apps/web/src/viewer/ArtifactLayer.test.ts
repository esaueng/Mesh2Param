import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  patchOutlinePositions,
  edgeOverlayKind,
  displayMaterialProperties,
  hidePatchTriangles,
  lineSegmentPositions,
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

  it("removes hidden patch triangles from rendering and raycasting without mutating the cached geometry", () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
      1, 1, 0,
    ], 3));
    geometry.setIndex([0, 1, 2, 1, 3, 2]);
    const originalIndices = Array.from(geometry.getIndex()!.array);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
    const object = new THREE.Group();
    object.add(mesh);

    expect(hidePatchTriangles(object, [
      { triangleStart: 0, triangleEndExclusive: 1, patchId: "patch-a", semanticIds: ["patch-a"] },
      { triangleStart: 1, triangleEndExclusive: 2, patchId: "patch-b", semanticIds: ["patch-b"] },
    ], ["patch-a"])).toBe(1);

    expect(mesh.geometry).not.toBe(geometry);
    expect(Array.from(geometry.getIndex()!.array)).toEqual(originalIndices);
    expect(Array.from(mesh.geometry.getIndex()!.array)).toEqual([0, 0, 0, 1, 3, 2]);

    object.updateMatrixWorld(true);
    const hiddenRay = new THREE.Raycaster(
      new THREE.Vector3(0.2, 0.2, 1),
      new THREE.Vector3(0, 0, -1),
    );
    const visibleRay = new THREE.Raycaster(
      new THREE.Vector3(0.8, 0.8, 1),
      new THREE.Vector3(0, 0, -1),
    );
    expect(hiddenRay.intersectObject(mesh)).toEqual([]);
    expect(visibleRay.intersectObject(mesh)).toHaveLength(1);
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

  it("prefers exact sampled CAD edges for reconstructed B-Reps", () => {
    expect(edgeOverlayKind("reconstructed", false, true, false, 2_876, false, true))
      .toBe("analytic");
    expect(edgeOverlayKind("reconstructed", false, true, false, 2_876, true, true))
      .toBe("creases");
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

describe("analytic edge geometry", () => {
  it("expands indexed GL line pairs without introducing triangle boundaries", () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute([
      0, 0, 0,
      1, 0, 0,
      1, 1, 0,
    ], 3));
    geometry.setIndex([0, 1, 1, 2]);

    expect(lineSegmentPositions(geometry)).toEqual([
      0, 0, 0,
      1, 0, 0,
      1, 0, 0,
      1, 1, 0,
    ]);
  });

  it("expands quantized interleaved GL line pairs", () => {
    const geometry = new THREE.BufferGeometry();
    const vertices = new THREE.InterleavedBuffer(new Uint16Array([
      0, 0, 0, 0,
      0xffff, 0, 0, 0,
      0xffff, 0xffff, 0, 0,
    ]), 4);
    geometry.setAttribute(
      "position",
      new THREE.InterleavedBufferAttribute(vertices, 3, 0, true),
    );
    geometry.setIndex(new THREE.Uint16BufferAttribute([0, 1, 1, 2], 1));

    expect(lineSegmentPositions(geometry)).toEqual([
      0, 0, 0,
      1, 0, 0,
      1, 0, 0,
      1, 1, 0,
    ]);
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

describe("patch outline", () => {
  function quadRanges(): SelectionRange[] {
    return [{ triangleStart: 0, triangleEndExclusive: 2, patchId: "patch.quad", semanticIds: [] }];
  }
  function quad(indexed: boolean): THREE.BufferGeometry {
    const geometry = new THREE.BufferGeometry();
    if (indexed) {
      geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], 3));
      geometry.setIndex([0, 1, 2, 0, 2, 3]);
    } else {
      // Two triangles with duplicated corner vertices, as an STL-derived mesh has.
      geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0], 3));
    }
    return geometry;
  }

  it("keeps only the boundary edges of the selected patch", () => {
    for (const indexed of [true, false]) {
      const positions = patchOutlinePositions(quad(indexed), quadRanges(), "patch.quad");
      // Four boundary segments of the unit square; the shared diagonal is dropped.
      expect(positions.length).toBe(4 * 6);
      const lengths = [];
      for (let item = 0; item < positions.length; item += 6) {
        const dx = positions[item + 3]! - positions[item]!;
        const dy = positions[item + 4]! - positions[item + 1]!;
        lengths.push(Math.hypot(dx, dy));
      }
      expect(lengths.every((length) => Math.abs(length - 1) < 1e-9)).toBe(true);
    }
  });

  it("returns nothing without a selection or for a patch outside the ranges", () => {
    expect(patchOutlinePositions(quad(true), quadRanges(), null)).toEqual([]);
    expect(patchOutlinePositions(quad(true), quadRanges(), "patch.other")).toEqual([]);
  });

  it("respects the triangle offset of later meshes in the same object", () => {
    const ranges: SelectionRange[] = [{ triangleStart: 10, triangleEndExclusive: 12, patchId: "p", semanticIds: [] }];
    expect(patchOutlinePositions(quad(true), ranges, "p", 10).length).toBe(24);
    expect(patchOutlinePositions(quad(true), ranges, "p", 0)).toEqual([]);
  });
});
