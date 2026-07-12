import { describe, expect, it } from "vitest";
import type { ProjectWorkingDocument } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import { nextAction, regenerationAction, reconstructedRevealPreferences } from "./pipeline";

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

  it("regenerates a completed parametric STEP through the validated exporter", () => {
    const vm = completedWorkspace({ cadgraph: { features: [] } });

    expect(regenerationAction(vm)).toMatchObject({
      label: "Regenerate STEP",
      operation: "export",
      disabled: false,
    });
  });

  it("regenerates a browser-local faceted STEP from its preserved STL", () => {
    const vm = completedWorkspace({
      cadgraph: null,
      source: { format: "stl", scaleFactor: 1, declaredUnits: "mm" },
    });

    expect(regenerationAction(vm)).toMatchObject({
      label: "Regenerate STEP",
      operation: "reconstruct",
      settings: { mode: "faceted" },
      disabled: false,
    });
  });

  it("disables STEP regeneration while another geometry job is active", () => {
    const vm = completedWorkspace({ cadgraph: { features: [] } });
    vm.activeJob = { job: { kind: "export" } } as WorkspaceViewModel["activeJob"];

    expect(regenerationAction(vm)).toMatchObject({
      disabled: true,
      reason: "A job is already running.",
    });
  });
});

function completedWorkspace(overrides: Record<string, unknown>): WorkspaceViewModel {
  const state = {
    units: "mm",
    source: { format: "stl", scaleFactor: 1, declaredUnits: "mm" },
    patches: [],
    cadgraph: null,
    validation: { brepValid: true, stepReimportValid: true },
    artifacts: [],
    settings: {},
    ...overrides,
  } as unknown as ProjectWorkingDocument;
  return {
    project: { units: "mm", state },
    activeJob: null,
    artifacts: [{ name: "model.step", kind: "step" }],
    workerReady: true,
    serverWritable: true,
  } as unknown as WorkspaceViewModel;
}
