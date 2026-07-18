import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SurfacePatch } from "../state/types";
import { mergeBlockReason, PatchPanel } from "./PatchPanel";

function patch(overrides: Partial<SurfacePatch> & { id: string }): SurfacePatch {
  return {
    type: "plane",
    triangleCount: 12,
    areaMm2: 100,
    residualsMm: { rms: 0.001, median: 0.001, p95: 0.002, max: 0.003 },
    confidence: 1,
    locked: false,
    ...overrides,
  } as SurfacePatch;
}

const PATCHES: SurfacePatch[] = [
  patch({ id: "patch.a", type: "plane", fit: { normal: [0, 0, 1] } }),
  patch({ id: "patch.b", type: "plane", fit: { normal: [0, 0, 1] } }),
  patch({ id: "patch.c", type: "freeform", confidence: 0 }),
];

afterEach(cleanup);

describe("mergeBlockReason", () => {
  it("mirrors the server preconditions", () => {
    expect(mergeBlockReason(PATCHES[0], PATCHES[1])).toBeNull();
    expect(mergeBlockReason(PATCHES[0], PATCHES[2])).toContain("same classification");
    expect(mergeBlockReason(patch({ id: "x", locked: true }), PATCHES[0])).toContain("Unlock");
    expect(
      mergeBlockReason(patch({ id: "x", fit: { normal: [1, 0, 0] } }), PATCHES[0]),
    ).toContain("identical fitted parameters");
    expect(mergeBlockReason(undefined, PATCHES[0])).toContain("exactly two");
  });
});

describe("PatchPanel", () => {
  it("locks a patch and reclassifies the selected one", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    render(
      <PatchPanel
        patches={PATCHES}
        selectedPatchId="patch.c"
        disabled={false}
        onSelect={() => {}}
        onUpdate={onUpdate}
        onMerge={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Lock patch.a" }));
    expect(onUpdate).toHaveBeenCalledWith("patch.a", { locked: true });

    await user.selectOptions(screen.getByRole("combobox", { name: "Reclassify selected patch" }), "torus");
    expect(onUpdate).toHaveBeenCalledWith("patch.c", { classification: "torus" });
  });

  it("merges exactly two compatible patches and blocks incompatible pairs", async () => {
    const user = userEvent.setup();
    const onMerge = vi.fn();
    render(
      <PatchPanel
        patches={PATCHES}
        selectedPatchId={null}
        disabled={false}
        onSelect={() => {}}
        onUpdate={() => {}}
        onMerge={onMerge}
      />,
    );

    const merge = screen.getByRole("button", { name: /Merge/ });
    expect(merge).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Select patch.a for merge" }));
    await user.click(screen.getByRole("checkbox", { name: "Select patch.c for merge" }));
    expect(merge).toBeDisabled();
    expect(merge).toHaveAttribute("title", expect.stringContaining("same classification"));

    await user.click(screen.getByRole("checkbox", { name: "Select patch.c for merge" }));
    await user.click(screen.getByRole("checkbox", { name: "Select patch.b for merge" }));
    expect(merge).toBeEnabled();
    await user.click(merge);
    expect(onMerge).toHaveBeenCalledWith(["patch.a", "patch.b"]);
  });

  it("offers boundary continuity between adjacent freeform regions", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const regions: SurfacePatch[] = [
      patch({ id: "patch.r1", type: "freeform", neighborIds: ["patch.r2", "patch.a"] }),
      patch({ id: "patch.r2", type: "freeform", neighborIds: ["patch.r1"] }),
      patch({ id: "patch.a", type: "plane", neighborIds: ["patch.r1"] }),
    ];
    render(
      <PatchPanel
        patches={regions}
        selectedPatchId="patch.r1"
        disabled={false}
        onSelect={() => {}}
        onUpdate={onUpdate}
        onMerge={() => {}}
      />,
    );

    // Only the freeform neighbor gets a boundary control; the plane does not.
    const control = screen.getByRole("combobox", { name: "Boundary continuity to patch.r2" });
    expect(screen.queryByRole("combobox", { name: "Boundary continuity to patch.a" })).toBeNull();
    expect(control).toHaveValue("crease");
    await user.selectOptions(control, "smooth");
    expect(onUpdate).toHaveBeenCalledWith("patch.r1", { smoothBoundaryIds: ["patch.r2"] });
  });

  it("reflects and clears an existing smooth declaration, locked blocks edits", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const regions: SurfacePatch[] = [
      patch({
        id: "patch.r1",
        type: "freeform",
        neighborIds: ["patch.r2"],
        smoothBoundaryIds: ["patch.r2"],
      }),
      patch({ id: "patch.r2", type: "freeform", neighborIds: ["patch.r1"], locked: true }),
    ];
    render(
      <PatchPanel
        patches={regions}
        selectedPatchId="patch.r1"
        disabled={false}
        onSelect={() => {}}
        onUpdate={onUpdate}
        onMerge={() => {}}
      />,
    );
    const control = screen.getByRole("combobox", { name: "Boundary continuity to patch.r2" });
    expect(control).toHaveValue("smooth");
    // The neighbor is locked, so the boundary cannot be edited from this side.
    expect(control).toBeDisabled();
    await user.selectOptions(control, "crease").catch(() => {});
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("keeps split explicitly unavailable and locked patches read-only", () => {
    render(
      <PatchPanel
        patches={[patch({ id: "patch.x", locked: true })]}
        selectedPatchId="patch.x"
        disabled={false}
        onSelect={() => {}}
        onUpdate={() => {}}
        onMerge={() => {}}
      />,
    );
    const split = screen.getByRole("button", { name: /Split/ });
    expect(split).toBeDisabled();
    expect(split).toHaveAttribute("title", expect.stringContaining("not implemented"));
    expect(screen.getByRole("combobox", { name: "Reclassify selected patch" })).toBeDisabled();
  });
});
