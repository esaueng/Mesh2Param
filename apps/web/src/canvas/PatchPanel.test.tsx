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
