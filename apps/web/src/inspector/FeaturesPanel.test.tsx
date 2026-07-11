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
});
