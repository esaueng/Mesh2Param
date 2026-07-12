import { describe, expect, it } from "vitest";
import type { ProjectWorkingDocument } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import { nextAction, reconstructedRevealPreferences } from "./pipeline";

describe("canvas pipeline actions", () => {
  it("labels the source-bound faceted fallback explicitly", () => {
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

    expect(nextAction(vm)).toMatchObject({
      kind: "faceted",
      label: "Generate faceted STEP",
      operation: "reconstruct",
      settings: { mode: "faceted" },
      disabled: false,
    });
  });

  it("reveals reconstructed CAD as a shaded solid instead of inherited mesh wireframe", () => {
    expect(reconstructedRevealPreferences()).toEqual({
      mode: "reconstructed",
      resultOpacity: 1,
      shading: "shaded",
      edges: true,
    });
  });
});
