import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import baseGraphDocument from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import type { WorkspaceActions, WorkspaceViewModel } from "./types";
import { TopBar } from "./TopBar";

describe("TopBar automatic reconstruction capability", () => {
  it("disables the unsupported Flange inference entry point with its reason", () => {
    const reason = "Automatic inference currently supports only the L-bracket with four through holes.";
    const flangeGraph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    flangeGraph.extensions = { "mesh2param.dev/sample": { slug: "flange" } };
    const vm = {
      project: {
        name: "Flange",
        state: {
          source: { id: "source-1" },
          settings: { automaticReconstruction: { supported: false, sampleId: "flange", reason } },
          cadgraph: flangeGraph,
        },
      },
      activeJob: null,
      serverWritable: true,
      workerReady: true,
    } as unknown as WorkspaceViewModel;
    const actions = {
      canUndo: false,
      canRedo: false,
      openStart: vi.fn(),
      setStep: vi.fn(),
      run: vi.fn(async () => undefined),
      saveProject: vi.fn(async () => undefined),
      renameProject: vi.fn(async () => undefined),
      undo: vi.fn(),
      redo: vi.fn(),
    } as unknown as WorkspaceActions;

    render(<TopBar vm={vm} actions={actions} onToggleShortcuts={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Auto reconstruct" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", reason);
  });
});
