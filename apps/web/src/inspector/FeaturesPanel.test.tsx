import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import baseGraphDocument from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { FeaturesPanel } from "./FeaturesPanel";

afterEach(cleanup);

describe("FeaturesPanel candidate histories", () => {
  it("replaces the editable graph and rebuilds when a valid persisted candidate is selected", async () => {
    const user = userEvent.setup();
    const candidateGraph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    candidateGraph.extensions = {
      ...candidateGraph.extensions,
      "mesh2param.dev/reconstruction": { candidate: "nominal-preview" },
    };
    const updateCadgraph = vi.fn(async () => undefined);
    const run = vi.fn(async () => undefined);
    const vm = {
      project: {
        id: "project-1",
        units: "mm",
        state: {
          source: { id: "source-1" },
          cadgraph: baseGraphDocument,
          settings: {
            selectedCandidate: "measured",
            candidateHistories: [{
              label: "nominal-preview",
              score: 0.92,
              valid: true,
              rejectionReason: null,
              featureCount: candidateGraph.features.length,
              cadgraph: candidateGraph,
              kernel: { success: true },
              comparison: null,
            }],
          },
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      updateCadgraph,
      run,
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);
    await user.click(screen.getByRole("button", { name: /nominal-preview/i }));

    expect(updateCadgraph).toHaveBeenCalledWith(candidateGraph, "Select nominal-preview candidate");
    expect(updateCadgraph.mock.invocationCallOrder[0]).toBeLessThan(run.mock.invocationCallOrder[0] ?? 0);
    expect(run).toHaveBeenCalledWith("rebuild");
  });

  it("explains unsupported Flange inference and rebuilds its exact CADGraph", async () => {
    const user = userEvent.setup();
    const reason = "Automatic inference currently supports only the L-bracket with four through holes.";
    const run = vi.fn(async () => undefined);
    const flangeGraph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    flangeGraph.extensions = { "mesh2param.dev/sample": { slug: "flange" } };
    const vm = {
      project: {
        id: "project-flange",
        units: "mm",
        state: {
          source: { id: "source-1" },
          cadgraph: flangeGraph,
          settings: { automaticReconstruction: { supported: false, sampleId: "flange", reason } },
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run,
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    const panel = render(<FeaturesPanel vm={vm} actions={actions} />);

    expect(panel.getByText(reason)).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Auto reconstruct" })).toBeDisabled();
    await user.click(panel.getByRole("button", { name: "Rebuild sample CADGraph" }));
    expect(run).toHaveBeenCalledWith("rebuild");
  });

  it("starts an explicit source-preserving faceted fallback for an analyzed STL", async () => {
    const user = userEvent.setup();
    const run = vi.fn(async () => undefined);
    const vm = {
      project: {
        id: "project-upload",
        units: "mm",
        state: {
          source: { sha256: "a".repeat(64), format: "stl", declaredUnits: "mm", scaleFactor: 1 },
          cadgraph: null,
          patches: [{ id: "patch.freeform", type: "freeform", areaMm2: 100, locked: false }],
          diagnostics: {
            connectedComponentCount: 2,
            openBoundaryCount: 3,
            triangleCount: 45_615,
          },
          settings: {},
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run,
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);
    expect(screen.getByText(/2 components, 3 open boundaries, 45,615 triangles/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sew source facets and create STEP" }));

    expect(run).toHaveBeenCalledWith("reconstruct", {
      mode: "faceted",
      sewingTolerance: 0.05,
    });
  });

  it("converts the physical default and maximum into project units", () => {
    const vm = {
      project: {
        id: "project-inch",
        units: "in",
        state: {
          source: { sha256: "a".repeat(64), format: "stl", declaredUnits: "in", scaleFactor: 1 },
          cadgraph: null,
          patches: [{ id: "patch.freeform", type: "freeform", areaMm2: 100, locked: false }],
          diagnostics: null,
          settings: {},
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run: vi.fn(async () => undefined),
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);

    const tolerance = screen.getByRole("spinbutton", { name: /Sewing tolerance/i });
    expect(tolerance).toHaveValue(0.05 / 25.4);
    expect(tolerance).toHaveAttribute("max", String(10 / 25.4));
  });

  it("hydrates and reuses the persisted tolerance for an active faceted fallback", async () => {
    const user = userEvent.setup();
    const run = vi.fn(async () => undefined);
    const facetedGraph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    facetedGraph.extensions = {
      "mesh2param.dev/facetedFallback": { nonParametric: true, sourcePreserved: true },
    };
    facetedGraph.features = [{
      id: "feature.faceted-source",
      name: "Imported source facets",
      operation: "importedFaceted",
      booleanMode: "base",
      order: 0,
      dependencies: [],
      suppressed: false,
      sourceEvidence: [],
      confidence: 1,
      userLocks: [],
      overrides: [],
      semanticOutputs: [],
      sourceArtifactId: "artifact.source",
      meshSha256: "a".repeat(64),
      intent: "fallback",
      sewingTolerance: 0.4,
    }];
    const vm = {
      project: {
        id: "project-faceted",
        units: "mm",
        state: {
          source: { sha256: "a".repeat(64), format: "stl", declaredUnits: "mm", scaleFactor: 1 },
          cadgraph: facetedGraph,
          patches: [],
          diagnostics: null,
          settings: { facetedFallback: { sewingToleranceMm: 0.2 } },
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run,
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);
    expect(screen.getByRole("spinbutton", { name: /Sewing tolerance \(project units\)/i })).toHaveValue(0.4);
    expect(screen.getByText(/no analytic source history or measured mesh deviation/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sew source facets and create STEP" }));

    expect(run).toHaveBeenCalledWith("reconstruct", {
      mode: "faceted",
      sewingTolerance: 0.4,
    });
  });

  it("preserves an existing analytic CADGraph instead of replacing it with a faceted proxy", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    const vm = {
      project: {
        id: "project-analytic",
        units: "mm",
        state: {
          source: { sha256: "a".repeat(64), format: "stl", declaredUnits: "mm", scaleFactor: 1 },
          cadgraph: graph,
          patches: [{ id: "patch.plane", type: "plane", areaMm2: 100, locked: false }],
          diagnostics: null,
          settings: {},
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run: vi.fn(async () => undefined),
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);

    expect(screen.getByText(/Existing editable CADGraph preserved/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sew source facets and create STEP" })).toBeDisabled();
  });

  it("preserves downstream edits on a faceted base instead of rerunning the one-feature fallback", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    const downstream = structuredClone(graph.features[0]!);
    downstream.id = "feature.downstream-edit";
    downstream.name = "Downstream edit";
    downstream.order = 1;
    downstream.dependencies = ["feature.faceted-source"];
    graph.extensions = { "mesh2param.dev/facetedFallback": { nonParametric: true } };
    graph.features[0] = {
      ...graph.features[0],
      id: "feature.faceted-source",
      operation: "importedFaceted",
      booleanMode: "base",
      sourceArtifactId: "artifact.source",
      meshSha256: "a".repeat(64),
      intent: "fallback",
      sewingTolerance: 0.05,
    } as CADGraph["features"][number];
    graph.features.push(downstream);
    const vm = {
      project: {
        id: "project-faceted-edited",
        units: "mm",
        state: {
          source: { sha256: "a".repeat(64), format: "stl", declaredUnits: "mm", scaleFactor: 1 },
          cadgraph: graph,
          analysis: null,
          patches: [],
          diagnostics: null,
          settings: {},
        },
      },
      artifacts: [],
      selectedFeatureId: null,
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      setStep: vi.fn(),
      selectFeature: vi.fn(),
      run: vi.fn(async () => undefined),
      cancelJob: vi.fn(async () => undefined),
    } as unknown as WorkspaceActions;

    render(<FeaturesPanel vm={vm} actions={actions} />);

    expect(screen.getByText(/Existing editable CADGraph preserved/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sew source facets and create STEP" })).toBeDisabled();
  });
});
