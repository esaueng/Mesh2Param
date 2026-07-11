import { describe, expect, it } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import baseGraphDocument from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import type { ProjectWorkingDocument } from "../state/types";
import { automaticReconstructionCapability } from "./automaticReconstruction";

function documentWith(graph: CADGraph, settings: ProjectWorkingDocument["settings"] = {}) {
  return { cadgraph: graph, settings } as unknown as ProjectWorkingDocument;
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

  it("keeps automatic inference available for uploads and the supported bracket sample", () => {
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
    expect(automaticReconstructionCapability({ cadgraph: null, settings: staleSettings }).supported).toBe(true);
  });
});
