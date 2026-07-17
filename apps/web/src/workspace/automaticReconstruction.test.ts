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

  it("refuses freeform geometry even with opposing cap evidence", () => {
    // Cap congruence alone does not guarantee the exact prismatic backend path
    // succeeds; its mesh-agreement gates run only at reconstruct time.
    const document = documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph);
    document.cadgraph = null;
    document.analysis = {
      ...(document.analysis ?? {}),
      patches: [
        { id: "patch.curved-sides", type: "freeform", areaMm2: 15_062, triangleCount: 3_764, confidence: 0, locked: false },
        { id: "patch.top", type: "plane", areaMm2: 604.476, fit: { normal: [0, 0, 1] }, triangleCount: 198, confidence: 1, locked: false },
        { id: "patch.bottom", type: "plane", areaMm2: 604.476, fit: { normal: [0, 0, -1] }, triangleCount: 198, confidence: 1, locked: false },
      ],
    };
    const capability = automaticReconstructionCapability(document);
    expect(capability.supported).toBe(false);
    expect(capability.reason).toMatch(/faceted STEP fallback/i);
  });

  it("refuses a gable-shaped analysis despite an accepted prismatic candidate", () => {
    // samples/curved-benchmark/bspline-soft-gable-plate: 2 freeform roof patches +
    // 5 planes with congruent pentagon end walls produce an accepted candidate at
    // ~0.88 confidence, yet exact reconstruction fails its geometric gates and dies
    // with the L-bracket freeform-remainder error. The capability must refuse so the
    // pipeline offers the curved STEP branch instead.
    const document = documentWith(structuredClone(baseGraphDocument) as unknown as CADGraph);
    document.cadgraph = null;
    document.analysis = {
      ...(document.analysis ?? {}),
      patches: [
        { id: "patch.roof-left", type: "freeform", areaMm2: 1_050, triangleCount: 900, confidence: 0, locked: false },
        { id: "patch.roof-right", type: "freeform", areaMm2: 1_050, triangleCount: 900, confidence: 0, locked: false },
        { id: "patch.cap-front", type: "plane", areaMm2: 350, fit: { normal: [0, 1, 0] }, triangleCount: 120, confidence: 1, locked: false },
        { id: "patch.cap-back", type: "plane", areaMm2: 350, fit: { normal: [0, -1, 0] }, triangleCount: 120, confidence: 1, locked: false },
        { id: "patch.side-left", type: "plane", areaMm2: 400, fit: { normal: [-1, 0, 0] }, triangleCount: 100, confidence: 1, locked: false },
        { id: "patch.side-right", type: "plane", areaMm2: 400, fit: { normal: [1, 0, 0] }, triangleCount: 100, confidence: 1, locked: false },
        { id: "patch.bottom", type: "plane", areaMm2: 1_800, fit: { normal: [0, 0, -1] }, triangleCount: 200, confidence: 1, locked: false },
      ],
      prismaticCandidate: {
        accepted: true,
        confidence: 0.878,
        profiles: [[{ kind: "line" }, { kind: "line" }, { kind: "line" }, { kind: "line" }, { kind: "line" }]],
      },
    };
    const capability = automaticReconstructionCapability(document);
    expect(capability.supported).toBe(false);
    expect(capability.reason).toContain("2 non-plane/cylinder patches");
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
