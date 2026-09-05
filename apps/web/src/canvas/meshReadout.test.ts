import { describe, expect, it } from "vitest";
import type { MeshDiagnostics } from "../state/types";
import { diagnosticRows } from "./meshReadout";

function diagnostics(overrides: Partial<MeshDiagnostics> = {}): MeshDiagnostics {
  return {
    format: "stl",
    encoding: "binary",
    byteSize: 1_000,
    sha256: "0".repeat(64),
    rawVertexCount: 3_600,
    weldedVertexCount: 1_200,
    duplicateVertexCount: 2_400,
    triangleCount: 2_400,
    connectedComponentCount: 1,
    bounds: [[0, 0, 0], [80, 40, 12.5]],
    boundingDimensions: [80, 40, 12.5],
    coordinateRange: [0, 80],
    surfaceArea: 9_400.123,
    closedVolume: 38_000.4567,
    watertight: true,
    windingConsistent: true,
    degenerateTriangleCount: 0,
    duplicateFaceCount: 0,
    nonManifoldEdgeCount: 0,
    openBoundaryEdgeCount: 0,
    openBoundaryCount: 0,
    selfIntersectionStatus: "none",
    warnings: [],
    ...overrides,
  } as MeshDiagnostics;
}

describe("diagnosticRows", () => {
  it("reports a healthy closed mesh without defect rows", () => {
    const rows = diagnosticRows(diagnostics(), "mm");
    const byLabel = Object.fromEntries(rows.map((row) => [row.label, row]));
    expect(rows.map((row) => row.label)).toEqual(["Triangles", "Vertices", "Bodies", "Watertight", "Winding", "Area", "Volume"]);
    expect(byLabel["Triangles"]?.value).toBe("2,400");
    expect(byLabel["Vertices"]?.value).toBe("1,200 (3,600 raw)");
    expect(byLabel["Watertight"]).toMatchObject({ value: "yes", tone: "ok" });
    expect(byLabel["Volume"]?.value).toBe("38,000.46 mm³");
    expect(byLabel["Area"]?.value).toBe("9,400.12 mm²");
  });

  it("surfaces open, non-manifold, and multi-body defects as warnings", () => {
    const rows = diagnosticRows(diagnostics({
      watertight: false,
      windingConsistent: false,
      closedVolume: null,
      openBoundaryEdgeCount: 12,
      nonManifoldEdgeCount: 3,
      degenerateTriangleCount: 1,
      connectedComponentCount: 2,
      duplicateVertexCount: 0,
      rawVertexCount: 1_200,
    }), "in");
    const byLabel = Object.fromEntries(rows.map((row) => [row.label, row]));
    expect(byLabel["Vertices"]?.value).toBe("1,200");
    expect(byLabel["Bodies"]).toMatchObject({ value: "2", tone: "warn" });
    expect(byLabel["Watertight"]).toMatchObject({ value: "no", tone: "warn" });
    expect(byLabel["Winding"]).toMatchObject({ value: "inconsistent", tone: "warn" });
    expect(byLabel["Open edges"]).toMatchObject({ value: "12", tone: "warn" });
    expect(byLabel["Non-manifold"]).toMatchObject({ value: "3", tone: "warn" });
    expect(byLabel["Degenerate"]).toMatchObject({ value: "1", tone: "warn" });
    expect(byLabel["Volume"]?.value).toBe("— (open mesh)");
    expect(byLabel["Area"]?.value).toBe("9,400.12 in²");
  });
});
