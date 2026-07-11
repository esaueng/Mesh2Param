import { describe, expect, it } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import baseGraphDocument from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import type { ProjectWorkingDocument } from "../state/types";
import { automaticReconstructionCapability } from "./automaticReconstruction";

function documentWith(graph: CADGraph, settings: ProjectWorkingDocument["settings"] = {}) {
  const analyzedPatches = [{ id: "patch.plane", type: "plane", areaMm2: 10, locked: false }];
  return {
    cadgraph: graph,
    settings,
    source: { sha256: "a".repeat(64), format: "stl" },
    analysis: {
      settings: {
        smoothAngleDeg: 12,
        planarFitToleranceMm: 0.005,
        cylinderFitToleranceMm: 0.01,
        minimumCylinderCoverageDeg: 300,
        maximumCylinderAxisNormalComponent: 0.05,
        minimumPatchAreaMm2: 1e-8,
        stableIdResolutionMm: 1e-5,
      },
      patches: analyzedPatches,
    },
    patches: analyzedPatches,
  } as unknown as ProjectWorkingDocument;
}

describe("automaticReconstructionCapability", () => {
  it("uses the authoritative project capability when present", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    graph.extensions = { "mesh2param.dev/sample": { slug: "flange" } };
    expect(automaticReconstructionCapability(documentWith(graph, {
      automaticReconstruction: {
        supported: false,
        sampleId: "flange",
        reason: "Flange inference is outside the current bounded scope.",
      },
    }))).toEqual({
      supported: false,
      sampleId: "flange",
      reason: "Flange inference is outside the current bounded scope.",
    });
  });

  it("recognizes older exact sample projects from their CADGraph extension", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    graph.extensions = { "mesh2param.dev/sample": { slug: "flange" } };
    const capability = automaticReconstructionCapability(documentWith(graph));
    expect(capability.supported).toBe(false);
    expect(capability.sampleId).toBe("flange");
    expect(capability.reason).toMatch(/L-bracket/i);
  });

  it("does not let project settings expand the engine's sample scope", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    graph.extensions = { "mesh2param.dev/sample": { slug: "flange" } };
    const capability = automaticReconstructionCapability(documentWith(graph, {
      automaticReconstruction: { supported: true, sampleId: "flange" },
    }));
    expect(capability.supported).toBe(false);
  });

  it("keeps automatic inference available for analyzed uploads and the supported bracket sample", () => {
    const upload = structuredClone(baseGraphDocument) as unknown as CADGraph;
    const bracket = structuredClone(baseGraphDocument) as unknown as CADGraph;
    bracket.extensions = { "mesh2param.dev/sample": { slug: "l-bracket-with-holes" } };
    expect(automaticReconstructionCapability(documentWith(upload)).supported).toBe(true);
    expect(automaticReconstructionCapability(documentWith(bracket)).supported).toBe(true);
  });

  it("ignores stale sample capability after its exact CADGraph is replaced", () => {
    const staleSettings = {
      automaticReconstruction: {
        supported: false,
        sampleId: "flange",
        reason: "Flange inference is outside the current bounded scope.",
      },
    };
    expect(automaticReconstructionCapability({
      cadgraph: null,
      settings: staleSettings,
      source: { sha256: "a".repeat(64), format: "stl" },
      analysis: documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph).analysis,
    } as unknown as ProjectWorkingDocument).supported).toBe(true);
  });

  it("requires analysis before enabling automatic inference for an upload", () => {
    const document = documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph);
    document.cadgraph = null;
    document.analysis = null;
    const capability = automaticReconstructionCapability(document);
    expect(capability.supported).toBe(false);
    expect(capability.reason).toMatch(/surface analysis again/i);
  });

  it("reports predominant freeform evidence and recommends the faceted fallback", () => {
    const document = documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph);
    document.cadgraph = null;
    document.analysis = {
      ...(document.analysis ?? {}),
      patches: [
        { id: "patch.freeform", type: "freeform", areaMm2: 99, triangleCount: 1, confidence: 0, locked: false },
        { id: "patch.plane", type: "plane", areaMm2: 1, triangleCount: 1, confidence: 1, locked: false },
      ],
    };
    document.patches = [{
      id: "patch.overridden",
      type: "plane",
      areaMm2: 100,
      triangleCount: 1,
      confidence: 1,
      locked: false,
    }];
    const capability = automaticReconstructionCapability(document);
    expect(capability.supported).toBe(false);
    expect(capability.reason).toContain("99.0%");
    expect(capability.reason).toMatch(/faceted STEP fallback/i);
  });

  it("requires complete persisted analysis settings before enabling inference", () => {
    const document = documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph);
    document.cadgraph = null;
    document.analysis = { patches: [{ id: "patch.plane", type: "plane", areaMm2: 10 }] };
    const capability = automaticReconstructionCapability(document);
    expect(capability.supported).toBe(false);
    expect(capability.reason).toMatch(/surface analysis again/i);
  });
});
