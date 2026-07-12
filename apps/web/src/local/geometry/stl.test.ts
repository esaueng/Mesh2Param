import { describe, expect, it } from "vitest";

import { analyzeStl } from "./stl";

function binaryStl(triangles: readonly (readonly [number, number, number])[][]): ArrayBuffer {
  const bytes = new ArrayBuffer(84 + triangles.length * 50);
  const view = new DataView(bytes);
  view.setUint32(80, triangles.length, true);
  triangles.forEach((triangle, triangleIndex) => {
    const offset = 84 + triangleIndex * 50 + 12;
    triangle.forEach((point, vertexIndex) => {
      point.forEach((value, axis) => view.setFloat32(offset + vertexIndex * 12 + axis * 4, value, true));
    });
  });
  return bytes;
}

describe("direct STL analysis", () => {
  it("diagnoses and meshes a watertight solid without an OCCT tessellation round-trip", () => {
    const result = analyzeStl(binaryStl([
      [[0, 0, 0], [0, 1, 0], [1, 0, 0]],
      [[0, 0, 0], [1, 0, 0], [0, 0, 1]],
      [[0, 0, 0], [0, 0, 1], [0, 1, 0]],
      [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    ]));

    expect(result.mesh.triangleCount).toBe(4);
    expect(result.mesh.vertexCount).toBe(12);
    expect(result.solid).toBe(true);
    expect(result.valid).toBe(true);
    expect(result.volume).toBeCloseTo(1 / 6);
    expect(result.diagnostics).toMatchObject({
      rawVertexCount: 12,
      weldedVertexCount: 4,
      duplicateVertexCount: 8,
      connectedComponentCount: 1,
      openBoundaryEdgeCount: 0,
      nonManifoldEdgeCount: 0,
      watertight: true,
      windingConsistent: true,
    });
  });

  it("reports open boundaries for a surface triangle", () => {
    const result = analyzeStl(binaryStl([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]]));
    expect(result.solid).toBe(false);
    expect(result.diagnostics).toMatchObject({
      openBoundaryEdgeCount: 3,
      openBoundaryCount: 1,
      watertight: false,
    });
  });
});
