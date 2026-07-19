// @vitest-environment node

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { validateCADGraph } from "@mesh2param/contracts";
import { OcctKernel } from "occt-wasm";
import { expect, it } from "vitest";

import { reconstructParametricStl } from "./reconstruction";
import type { ParametricStlGeometryRequest } from "./types";

const fixtures = [
  { slug: "spanner-sharp", detailMode: "full" as const, featureCount: 2, faceCount: 12, filleted: false, detailed: false },
  { slug: "spanner-filleted", detailMode: "full" as const, featureCount: 3, faceCount: 20, filleted: true, detailed: false },
  { slug: "spanner-filleted-embossed", detailMode: "full" as const, featureCount: 4, faceCount: 25, filleted: true, detailed: true },
];

it("reconstructs the sharp, filleted, and embossed spanner fixtures as parametric STEP", async () => {
  const kernel = await OcctKernel.init();
  try {
    for (const fixture of fixtures) {
      kernel.releaseAll();
      const path = resolve(process.cwd(), "../../samples/general-parametric-benchmark", fixture.slug, "source.stl");
      const file = await readFile(path);
      const bytes = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);
      const request: ParametricStlGeometryRequest = {
        id: fixture.slug,
        operation: "parametric-stl",
        bytes,
        source: {
          sha256: createHash("sha256").update(file).digest("hex"),
          originalFileName: `${fixture.slug}.stl`,
          byteSize: file.byteLength,
          declaredUnits: "mm",
          scaleFactor: 1,
        },
        units: "mm",
        tolerance: 0.05,
        detailMode: fixture.detailMode,
        deterministicSeed: 0x4d325006,
      };
      const result = reconstructParametricStl(kernel, request, () => undefined);

      expect(result.valid, fixture.slug).toBe(true);
      expect(result.solid, fixture.slug).toBe(true);
      expect(result.stepReimportValid, fixture.slug).toBe(true);
      expect(result.parametricReconstruction.acceptance, fixture.slug).toBe("strict");
      expect(result.parametricReconstruction.toleranceSatisfied, fixture.slug).toBe(true);
      expect(result.featureCount, fixture.slug).toBe(fixture.featureCount);
      expect(result.topologyCounts?.face, fixture.slug).toBe(fixture.faceCount);
      expect(validateCADGraph(result.graph), fixture.slug).toMatchObject({ valid: true });
      expect(result.graph.sketches[0]?.entities.some((entity) => entity.kind === "bspline"), fixture.slug).toBe(true);
      expect(result.graph.features.some((feature) => feature.operation === "fillet"), fixture.slug).toBe(fixture.filleted);
      expect(result.graph.features.some((feature) => feature.id === "feature.detail"), fixture.slug).toBe(fixture.detailed);
      expect(result.parametricReconstruction.comparison.distance.p95, fixture.slug).toBeLessThanOrEqual(0.05);
      expect(result.parametricReconstruction.comparison.relativeVolumeDelta, fixture.slug).toBeLessThanOrEqual(0.001);
      if (fixture.filleted) {
        expect(result.parametricReconstruction.filletRadius, fixture.slug).toBeCloseTo(1.5, 1);
        expect(result.surfaceCounts?.torus, fixture.slug).toBeGreaterThanOrEqual(1);
      }
      if (fixture.detailed) {
        const rectangle = result.graph.sketches.find((sketch) => sketch.id === "sketch.detail")?.entities[0];
        expect(rectangle?.kind, fixture.slug).toBe("rectangle");
        if (rectangle?.kind === "rectangle") {
          const dimensions = [rectangle.width, rectangle.height].sort((left, right) => left - right);
          expect(dimensions[0], fixture.slug).toBeCloseTo(6, 3);
          expect(dimensions[1], fixture.slug).toBeCloseTo(18, 3);
        }
        const detail = result.graph.features.find((feature) => feature.id === "feature.detail");
        expect(detail?.operation, fixture.slug).toBe("extrusion");
        if (detail?.operation === "extrusion") expect(detail.distance, fixture.slug).toBeCloseTo(0.4, 3);
      }
      expect(result.step).toContain("B_SPLINE_CURVE_WITH_KNOTS");
    }
  } finally {
    kernel[Symbol.dispose]();
  }
}, 120_000);

it("suppresses the shallow boss in functional mode and emits its residual mesh", async () => {
  const kernel = await OcctKernel.init();
  try {
    const slug = "spanner-filleted-embossed";
    const path = resolve(process.cwd(), "../../samples/general-parametric-benchmark", slug, "source.stl");
    const file = await readFile(path);
    const result = reconstructParametricStl(kernel, {
      id: slug,
      operation: "parametric-stl",
      bytes: file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength),
      source: {
        sha256: createHash("sha256").update(file).digest("hex"), originalFileName: `${slug}.stl`,
        byteSize: file.byteLength, declaredUnits: "mm", scaleFactor: 1,
      },
      units: "mm", tolerance: 0.05, detailMode: "functional", deterministicSeed: 0x4d325006,
    }, () => undefined);

    expect(result.graph.features).toHaveLength(3);
    expect(result.graph.features.some((feature) => feature.id === "feature.detail")).toBe(false);
    expect(result.suppressedRegions).toHaveLength(1);
    expect(result.suppressedMesh?.triangleCount).toBeGreaterThan(0);
    expect(result.parametricReconstruction.comparison.relativeVolumeDelta).toBeLessThanOrEqual(0.001);
  } finally {
    kernel[Symbol.dispose]();
  }
}, 60_000);
