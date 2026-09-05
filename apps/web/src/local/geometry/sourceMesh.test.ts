import { describe, expect, it } from "vitest";

import { parseStlForDisplay } from "./sourceMesh";

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

const TETRAHEDRON = [
  [[0, 0, 0], [0, 1, 0], [1, 0, 0]],
  [[0, 0, 0], [1, 0, 0], [0, 0, 1]],
  [[0, 0, 0], [0, 0, 1], [0, 1, 0]],
  [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
] as const as readonly (readonly [number, number, number])[][];

describe("source mesh display parsing", () => {
  it("reads a binary STL into a renderable triangle soup with its measured extent", () => {
    const parsed = parseStlForDisplay(binaryStl(TETRAHEDRON));

    expect(parsed.mesh.triangleCount).toBe(4);
    expect(parsed.mesh.vertexCount).toBe(12);
    expect(parsed.mesh.positions).toHaveLength(36);
    expect(parsed.mesh.indices).toHaveLength(12);
    expect(parsed.bounds).toEqual([[0, 0, 0], [1, 1, 1]]);
    expect(parsed.signedVolume).toBeCloseTo(1 / 6);
    // Three unit right triangles plus the equilateral face on side sqrt(2).
    expect(parsed.surfaceArea).toBeCloseTo(1.5 + Math.sqrt(3) / 2);
  });

  it("gives every vertex the facet normal of its own triangle", () => {
    const parsed = parseStlForDisplay(binaryStl([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]]));

    expect([...parsed.mesh.normals]).toEqual([0, 0, 1, 0, 0, 1, 0, 0, 1]);
  });

  it("reads an ASCII STL that is not a valid binary STL", () => {
    const text = `solid t
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 2 0 0
    vertex 0 2 0
  endloop
endfacet
endsolid t
`;
    const parsed = parseStlForDisplay(new TextEncoder().encode(text).buffer as ArrayBuffer);

    expect(parsed.mesh.triangleCount).toBe(1);
    expect(parsed.surfaceArea).toBeCloseTo(2);
  });

  it("refuses bytes that are neither a binary nor an ASCII STL", () => {
    expect(() => parseStlForDisplay(new TextEncoder().encode("not a mesh").buffer as ArrayBuffer))
      .toThrow(/does not contain complete triangular facets/);
  });

  it("refuses a non-finite coordinate rather than rendering it", () => {
    expect(() => parseStlForDisplay(binaryStl([[[0, 0, 0], [Number.NaN, 0, 0], [0, 1, 0]]])))
      .toThrow(/non-finite vertex coordinate/);
  });
});
