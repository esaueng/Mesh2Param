import { describe, expect, it } from "vitest";
import type { ProjectWorkingDocument } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import { nextAction } from "./pipeline";

describe("canvas pipeline actions", () => {
  it("offers curved first with the faceted fallback as the labeled alternate", () => {
    const patches = [{
      id: "patch.freeform",
      type: "freeform",
      areaMm2: 100,
      triangleCount: 45_615,
      confidence: 0,
      locked: false,
    }];
    const state = {
      units: "mm",
      source: {
        format: "stl",
        scaleFactor: 1,
        declaredUnits: "mm",
      },
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
        patches,
      },
      patches,
      cadgraph: null,
      validation: null,
      artifacts: [],
      settings: {},
    } as unknown as ProjectWorkingDocument;
    const vm = {
      project: { units: "mm", state },
      activeJob: null,
      artifacts: [],
      workerReady: true,
      serverWritable: true,
    } as unknown as WorkspaceViewModel;

    const action = nextAction(vm);
    expect(action).toMatchObject({
      kind: "curved",
      label: "Generate curved STEP",
      operation: "reconstruct",
      settings: { mode: "curved" },
      disabled: false,
    });
    expect(action.hint).toContain("approximate");
    expect(action.hint).toContain("not recovered design history");
    expect(action.alternate).toMatchObject({
      kind: "faceted",
      label: "Generate faceted STEP",
      operation: "reconstruct",
      settings: { mode: "faceted" },
      disabled: false,
    });
  });
});
