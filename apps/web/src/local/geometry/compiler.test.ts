// @vitest-environment node

import type { CADGraph } from "@mesh2param/contracts";
import { readFileSync } from "node:fs";
import { OcctKernel } from "occt-wasm";
import { expect, it } from "vitest";

import { compileCadGraph, compileStl } from "./compiler";

type Point = readonly [number, number, number];
type Triangle = readonly [Point, Point, Point];

function tetrahedron(offsetX: number): Triangle[] {
  const point = (x: number, y: number, z: number): Point => [x + offsetX, y, z];
  const a = point(0, 0, 0);
  const b = point(1, 0, 0);
  const c = point(0, 1, 0);
  const d = point(0, 0, 1);
  return [[a, c, b], [a, b, d], [a, d, c], [b, c, d]];
}

function binaryStl(triangles: readonly Triangle[]): ArrayBuffer {
  const bytes = new ArrayBuffer(84 + triangles.length * 50);
  const view = new DataView(bytes);
  view.setUint32(80, triangles.length, true);
  triangles.forEach((triangle, triangleIndex) => {
    const offset = 84 + triangleIndex * 50 + 12;
    triangle.forEach((point, vertexIndex) => {
      point.forEach((value, axis) => view.setFloat32(
        offset + vertexIndex * 12 + axis * 4,
        value,
        true,
      ));
    });
  });
  return bytes;
}

it("exports and reimports disconnected watertight STL components as multiple solids", async () => {
  const kernel = await OcctKernel.init();
  try {
    const result = compileStl(kernel, binaryStl([
      ...tetrahedron(0),
      ...tetrahedron(3),
    ]), 0.1);

    expect(result.valid).toBe(true);
    expect(result.solid).toBe(true);
    expect(result.stepReimportValid).toBe(true);
    expect(result.diagnostics?.connectedComponentCount).toBe(2);
    expect(kernel.getSubShapes(kernel.importStep(result.step), "solid")).toHaveLength(2);
  } finally {
    kernel[Symbol.dispose]();
  }
});

it("keeps the browser display LOD separate from STL and OBJ export tessellation", async () => {
  const graph = JSON.parse(readFileSync(
    new URL("../../../../../packages/contracts/tests/fixtures/base.cadgraph.json", import.meta.url),
    "utf8",
  )) as CADGraph;
  graph.projectTolerance.surfaceDeviation = 0.2;
  graph.projectTolerance.angularDeviationDeg = 20;
  const kernel = await OcctKernel.init();
  try {
    const result = compileCadGraph(kernel, graph);

    expect(result.exportMesh).toBeDefined();
    expect(result.exportMesh!.triangleCount).toBeLessThan(result.mesh.triangleCount);
    expect(result.edgeLines?.segmentCount).toBeGreaterThan(0);
  } finally {
    kernel[Symbol.dispose]();
  }
});
