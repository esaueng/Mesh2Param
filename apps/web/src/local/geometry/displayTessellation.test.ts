// @vitest-environment node

import { OcctKernel } from "occt-wasm";
import { describe, expect, it } from "vitest";

import {
  DISPLAY_ANGULAR_DEFLECTION,
  DISPLAY_EDGE_ANGULAR_DEFLECTION,
  DISPLAY_RELATIVE_LINEAR_DEFLECTION,
  MAX_DISPLAY_EDGE_SEGMENTS,
  displayTessellationOptions,
  edgeLinesFromWireframe,
} from "./displayTessellation";

describe("result display tessellation", () => {
  it.each([1, 10, 100])(
    "scales chordal tolerance for a diameter-%s cylinder while retaining angular detail",
    (diameter) => {
      const settings = displayTessellationOptions(
        {
          xmin: -diameter / 2,
          ymin: -diameter / 2,
          zmin: 0,
          xmax: diameter / 2,
          ymax: diameter / 2,
          zmax: diameter,
        },
        diameter,
        0.2,
      );
      const diagonal = Math.sqrt(3) * diameter;

      expect(settings.modelDiagonal).toBeCloseTo(diagonal, 12);
      expect(settings.mesh.linearDeflection)
        .toBeCloseTo(diagonal * DISPLAY_RELATIVE_LINEAR_DEFLECTION, 12);
      expect(settings.mesh.angularDeflection).toBeCloseTo(DISPLAY_ANGULAR_DEFLECTION, 12);
      expect(settings.edgeAngularDeflection)
        .toBeCloseTo(DISPLAY_EDGE_ANGULAR_DEFLECTION, 12);
      const radius = diameter / 2;
      const edgeSagitta = radius * (1 - Math.cos(settings.edgeAngularDeflection / 2));
      expect(edgeSagitta * (4_000 / diameter)).toBeLessThan(0.1);
    },
  );

  it("never loosens a stricter project tolerance", () => {
    const settings = displayTessellationOptions(
      { xmin: 0, ymin: 0, zmin: 0, xmax: 100, ymax: 100, zmax: 100 },
      1e-4,
      1e-3,
    );

    expect(settings.mesh.linearDeflection).toBe(1e-4);
    expect(settings.mesh.angularDeflection).toBe(1e-3);
    expect(settings.edgeAngularDeflection).toBe(1e-3);
  });

  it("tessellates exact browser cylinders smoothly across model scales", async () => {
    const kernel = await OcctKernel.init();
    try {
      for (const diameter of [1, 10, 100]) {
        const cylinder = kernel.makeCylinder(diameter / 2, diameter);
        try {
          const settings = displayTessellationOptions(
            kernel.getBoundingBox(cylinder, false),
            diameter,
            0.2,
          );
          const mesh = kernel.tessellate(cylinder, settings.mesh);
          const lines = edgeLinesFromWireframe(
            kernel.wireframe(cylinder, settings.edgeAngularDeflection),
          );

          expect(mesh.triangleCount).toBeGreaterThan(700);
          expect(mesh.triangleCount).toBeLessThan(5_000);
          expect(lines.segmentCount).toBeGreaterThan(1_400);
          expect(lines.segmentCount).toBeLessThan(10_000);
        } finally {
          kernel.release(cylinder);
        }
      }
    } finally {
      kernel[Symbol.dispose]();
    }
  });
});

describe("exact edge line conversion", () => {
  it("preserves every OCCT polyline as connected GL line pairs", () => {
    const lines = edgeLinesFromWireframe({
      points: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        1, 1, 0,
        3, 0, 0,
        3, 1, 0,
      ]),
      edgeGroups: new Int32Array([
        0, 9, 11,
        9, 6, 12,
      ]),
      pointCount: 15,
      edgeCount: 2,
    });

    expect(lines.positions).toEqual(new Float32Array([
      0, 0, 0,
      1, 0, 0,
      1, 1, 0,
      3, 0, 0,
      3, 1, 0,
    ]));
    expect(lines.indices).toEqual(new Uint32Array([0, 1, 1, 2, 3, 4]));
    expect(lines.segmentCount).toBe(3);
  });

  it("enforces the global segment cap after retaining every polyline endpoint", () => {
    const lines = edgeLinesFromWireframe({
      points: new Float32Array([
        0, 0, 0, 1, 0, 0,
        0, 1, 0, 1, 1, 0, 2, 1, 0, 3, 1, 0,
        0, 2, 0, 1, 2, 0,
        0, 3, 0, 1, 3, 0, 2, 3, 0, 3, 3, 0,
      ]),
      edgeGroups: new Int32Array([
        0, 6, 1,
        6, 12, 2,
        18, 6, 3,
        24, 12, 4,
      ]),
      pointCount: 36,
      edgeCount: 4,
    }, 4);

    expect(lines.segmentCount).toBe(4);
    expect(lines.segmentCount).toBeLessThanOrEqual(MAX_DISPLAY_EDGE_SEGMENTS);
    expect(lines.positions).toEqual(new Float32Array([
      0, 0, 0, 1, 0, 0,
      0, 1, 0, 3, 1, 0,
      0, 2, 0, 1, 2, 0,
      0, 3, 0, 3, 3, 0,
    ]));
  });
});
