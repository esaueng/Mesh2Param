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
  });
});

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
