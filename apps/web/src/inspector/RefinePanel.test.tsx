import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { RefinePanel } from "./RefinePanel";

afterEach(cleanup);

function fixture() {
  const feature = {
    id: "hole-1",
    name: "Through hole",
    operation: "hole",
    order: 1,
    dependencies: ["base"],
    suppressed: false,
    sourceEvidence: [],
    confidence: 0.98,
    userLocks: [],
    overrides: [],
    semanticOutputs: [],
    booleanMode: "subtractive",
    holeType: "through",
    position: { x: 0, y: 0, z: 0 },
    axis: { x: 0, y: 0, z: 1 },
    diameter: 10,
    depth: null,
  };
  const vm = {
    project: { id: "project-1", units: "mm", state: { cadgraph: { features: [feature] } } },
    selectedFeatureId: feature.id,
    activeJob: null,
    serverWritable: true,
    workerReady: true,
  } as unknown as WorkspaceViewModel;
  const actions = {
    setStep: vi.fn(),
    selectFeature: vi.fn(),
    updateCadgraph: vi.fn(async () => undefined),
    run: vi.fn(async () => undefined),
    cancelJob: vi.fn(async () => undefined),
  } as unknown as WorkspaceActions;
  return { vm, actions };
}

describe("RefinePanel parameter editing", () => {
  it("captures the input value before React releases the event and omits null through-hole depth", async () => {
    const user = userEvent.setup();
    const { vm, actions } = fixture();
    render(<RefinePanel vm={vm} actions={actions} />);
    const diameter = screen.getByRole("spinbutton", { name: "Diameter (mm)" });
    await user.clear(diameter);
    await user.type(diameter, "11");
    expect(diameter).toHaveValue(11);
    expect(screen.queryByRole("spinbutton", { name: "Depth (mm)" })).not.toBeInTheDocument();
  });

  it("commits Enter once and leaves rebuild actionable", async () => {
    const user = userEvent.setup();
    const { vm, actions } = fixture();
    render(<RefinePanel vm={vm} actions={actions} />);
    const diameter = screen.getByRole("spinbutton", { name: "Diameter (mm)" });

    await user.clear(diameter);
    await user.type(diameter, "11");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(actions.updateCadgraph).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Rebuild" }));

    expect(actions.updateCadgraph).toHaveBeenCalledTimes(1);
    expect(actions.run).toHaveBeenCalledWith("rebuild");
  });
});
