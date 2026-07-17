import { describe, expect, it } from "vitest";

import type { SourceAssetDescriptor } from "../../state/types";
import { inferBrowserPrismaticCadGraph } from "./prismatic";

describe("browser-local prismatic reconstruction", () => {
  it("recovers circular arcs instead of preserving polygon slices", () => {
    const positions = extrudedCapsule(20, 10, 8, 24);
    const source: SourceAssetDescriptor = {
      id: "source.capsule",
      originalFileName: "capsule.stl",
      format: "stl",
      encoding: "binary",
      sha256: "a".repeat(64),
      byteSize: positions.byteLength,
      declaredUnits: "mm",
      unitsConfirmed: true,
      scaleFactor: 1,
      state: "valid",
    };

    const result = inferBrowserPrismaticCadGraph(positions, source, "mm");

    expect(result).not.toBeNull();
    expect(result?.graph.features).toHaveLength(1);
    expect(result?.graph.features[0]).toMatchObject({ operation: "extrusion", distance: 8 });
    const kinds = result?.graph.sketches[0]?.entities.map((entity) => entity.kind);
    expect(kinds?.filter((kind) => kind === "circularArc").length).toBeGreaterThanOrEqual(2);
    expect(kinds?.filter((kind) => kind === "line")).toHaveLength(2);
    expect(kinds).not.toContain("polyline");
    expect(result?.analysis.profiles[0]).toHaveLength(kinds?.length ?? 0);
    expect(result?.analysis.relativeVolumeDelta).toBeLessThanOrEqual(0.01);
    expect(result?.graph.fitMetrics.volumeDifference).toBeGreaterThanOrEqual(0);
  });

  it("rejects matching cap fragments when the inferred extrusion volume does not match the source", () => {
    const positions = Float32Array.from([
      ...boxTriangles(-5, -4, -1, 1, -1, 1),
      ...boxTriangles(-4, 4, -2, 2, -2, 2),
      ...boxTriangles(4, 5, -1, 1, -1, 1),
    ]);
    const source: SourceAssetDescriptor = {
      id: "source.false-extrusion",
      originalFileName: "false-extrusion.stl",
      format: "stl",
      encoding: "binary",
      sha256: "b".repeat(64),
      byteSize: positions.byteLength,
      declaredUnits: "mm",
      unitsConfirmed: true,
      scaleFactor: 1,
      state: "valid",
    };

    expect(inferBrowserPrismaticCadGraph(positions, source, "mm")).toBeNull();
  });
});

function boxTriangles(
  xmin: number,
  xmax: number,
  ymin: number,
  ymax: number,
  zmin: number,
  zmax: number,
): number[] {
  const p = [
    [xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin], [xmin, ymax, zmin],
    [xmin, ymin, zmax], [xmax, ymin, zmax], [xmax, ymax, zmax], [xmin, ymax, zmax],
  ];
  const faces = [
    [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
    [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
    [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
  ];
  return faces.flatMap((face) => face.flatMap((index) => p[index]!));
}

function extrudedCapsule(length: number, diameter: number, height: number, arcSegments: number): Float32Array {
  const radius = diameter / 2;
  const halfStraight = (length - diameter) / 2;
  const profile: Array<[number, number]> = [];
  for (let index = 0; index <= arcSegments; index += 1) {
    const angle = -Math.PI / 2 + Math.PI * index / arcSegments;
    profile.push([halfStraight + Math.cos(angle) * radius, Math.sin(angle) * radius]);
  }
  for (let index = 0; index <= arcSegments; index += 1) {
    const angle = Math.PI / 2 + Math.PI * index / arcSegments;
    profile.push([-halfStraight + Math.cos(angle) * radius, Math.sin(angle) * radius]);
  }
  const unique = profile.filter((point, index) => index === 0 || point[0] !== profile[index - 1]![0] || point[1] !== profile[index - 1]![1]);
  const triangles: number[] = [];
  const push = (...points: Array<[number, number, number]>) => triangles.push(...points.flat());
  for (let index = 0; index < unique.length; index += 1) {
    const next = (index + 1) % unique.length;
    const lower: [number, number, number] = [unique[index]![0], unique[index]![1], 0];
    const lowerNext: [number, number, number] = [unique[next]![0], unique[next]![1], 0];
    const upper: [number, number, number] = [unique[index]![0], unique[index]![1], height];
    const upperNext: [number, number, number] = [unique[next]![0], unique[next]![1], height];
    push([0, 0, 0], lowerNext, lower);
    push([0, 0, height], upper, upperNext);
    push(lower, lowerNext, upperNext);
    push(lower, upperNext, upper);
  }
  return Float32Array.from(triangles);
}
