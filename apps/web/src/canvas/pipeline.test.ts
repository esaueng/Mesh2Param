import { describe, expect, it } from "vitest";
import type { ArtifactDescriptor, ProjectWorkingDocument } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import {
  analysisRerunAction,
  availableModes,
  nextAction,
  regenerationAction,
  reconstructedRevealPreferences,
} from "./pipeline";

describe("canvas pipeline actions", () => {
  it("offers exact browser-local reconstruction when the bounded probe accepts the mesh", () => {
    const patches = [{ id: "patch.source", type: "freeform", areaMm2: 100, triangleCount: 508, confidence: 1, locked: false }];
    const state = {
      units: "mm",
      source: { format: "stl", scaleFactor: 1, declaredUnits: "mm" },
      analysis: {
        settings: {
          smoothAngleDeg: 12, planarFitToleranceMm: 0.005, cylinderFitToleranceMm: 0.01,
          minimumCylinderCoverageDeg: 300, maximumCylinderAxisNormalComponent: 0.05,
          minimumPatchAreaMm2: 1e-8, stableIdResolutionMm: 1e-5,
        },
        patches,
        browserParametricCandidate: { accepted: true, family: "general-parametric-prismatic" },
      },
      patches,
      cadgraph: null,
      validation: null,
      artifacts: [],
      settings: {},
    } as unknown as ProjectWorkingDocument;
    const vm = {
      project: { units: "mm", state }, activeJob: null, artifacts: [], workerReady: true, serverWritable: true,
    } as unknown as WorkspaceViewModel;

    expect(nextAction(vm)).toMatchObject({
      kind: "reconstruct",
      operation: "reconstruct",
      label: "Reconstruct",
      disabled: false,
    });
  });

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

  it("reveals reconstructed CAD as a shaded solid instead of inherited mesh wireframe", () => {
    expect(reconstructedRevealPreferences()).toEqual({
      mode: "reconstructed",
      resultOpacity: 1,
      shading: "shaded",
      edges: true,
    });
  });

  it("surfaces the functional suppression residual layer with an explicit label", () => {
    const artifacts = [
      { name: "source.glb" },
      { name: "reconstructed.glb" },
      { name: "residual.glb" },
      { name: "suppressed-regions.json" },
    ] as ArtifactDescriptor[];

    expect(availableModes(artifacts)).toContainEqual({ mode: "residual", label: "Suppressed" });
  });

  it("regenerates a completed parametric STEP through the validated exporter", () => {
    const vm = completedWorkspace({ cadgraph: { features: [] } });

    expect(regenerationAction(vm)).toMatchObject({
      label: "Regenerate STEP",
      operation: "export",
      disabled: false,
    });
  });

  it("retries analytic recovery for a browser-local faceted STEP", () => {
    const vm = completedWorkspace({
      cadgraph: null,
      source: { format: "stl", scaleFactor: 1, declaredUnits: "mm" },
    });

    expect(regenerationAction(vm)).toMatchObject({
      kind: "reconstruct",
      label: "Recover smooth STEP",
      operation: "reconstruct",
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

  it("offers a non-destructive analysis rerun for a completed project", () => {
    const vm = completedWorkspace({ analysis: { settings: {}, patches: [] } });

    expect(analysisRerunAction(vm)).toMatchObject({
      kind: "analyze",
      label: "Rerun analysis",
      operation: "analyze",
      disabled: false,
    });
  });

  it("hides analysis rerun before a project has existing work", () => {
    const vm = completedWorkspace({
      analysis: null,
      patches: [],
      cadgraph: null,
      validation: null,
    });
    vm.artifacts = [];

    expect(analysisRerunAction(vm)).toBeNull();
  });

  it("disables analysis rerun while another geometry job is active", () => {
    const vm = completedWorkspace({ analysis: { settings: {}, patches: [] } });
    vm.activeJob = { job: { kind: "export" } } as WorkspaceViewModel["activeJob"];

    expect(analysisRerunAction(vm)).toMatchObject({
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
