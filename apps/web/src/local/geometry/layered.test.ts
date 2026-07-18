// @vitest-environment node

import { OcctKernel, type ShapeHandle, type Vec3 } from "occt-wasm";
import { expect, it } from "vitest";

import { compileCurvedStl } from "./compiler";

function periodicWire(kernel: OcctKernel, z: number): ShapeHandle {
  const points: Vec3[] = Array.from({ length: 32 }, (_value, index) => {
    const angle = index * Math.PI * 2 / 32;
    return {
      x: 12 * Math.cos(angle) + 1.5 * Math.cos(angle * 3),
      y: 7 * Math.sin(angle),
      z,
    };
  });
  return kernel.makeWire([kernel.interpolatePoints(points, true)]);
}

function hexagonalHole(kernel: OcctKernel, z: number): ShapeHandle {
  const points: Vec3[] = Array.from({ length: 6 }, (_value, index) => {
    const angle = index * Math.PI * 2 / 6;
    return { x: 2.2 * Math.cos(angle), y: 2.2 * Math.sin(angle), z };
  });
  return kernel.makeWire(points.map((point, index) => kernel.makeLineEdge(
    point,
    points[(index + 1) % points.length]!,
  )));
}

it("rebuilds a layered STL with genuine curved STEP surfaces", async () => {
  const kernel = await OcctKernel.init();
  try {
    const outer = kernel.loft([periodicWire(kernel, 0), periodicWire(kernel, 10)], true, false);
    const hole = kernel.extrude(kernel.makeFace(hexagonalHole(kernel, 0)), 0, 0, 10);
    const exact = kernel.cut(outer, hole);
    const stl = kernel.exportStl(exact, 0.05, true);
    const bytes = new TextEncoder().encode(stl);

    const result = compileCurvedStl(
      kernel,
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
      0.1,
    );

    expect(result.valid).toBe(true);
    expect(result.solid).toBe(true);
    expect(result.stepReimportValid).toBe(true);
    expect(result.curvedReconstruction?.faceSurfaces.extrusion).toBeGreaterThan(0);
    expect(result.curvedReconstruction?.reconstructionMode).toBe("representative-extrusion");
    expect(result.curvedReconstruction?.outerProfileCount).toBe(1);
    expect(result.curvedReconstruction?.holeTrackCount).toBe(1);
    expect(result.curvedReconstruction?.relativeVolumeDelta).toBeLessThan(0.02);
    expect(result.step).toContain("SURFACE_OF_LINEAR_EXTRUSION");
    expect(result.step).toContain("B_SPLINE_CURVE_WITH_KNOTS");
  } finally {
    kernel[Symbol.dispose]();
  }
}, 20_000);
