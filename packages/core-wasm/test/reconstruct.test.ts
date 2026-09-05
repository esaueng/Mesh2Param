/**
 * The built WebAssembly package, run in Node against two real corpus meshes.
 *
 * This is the only test that exercises the whole path the browser will take —
 * bindings, options, progress, GLB writer — so it loads `pkg/` from disk rather
 * than importing the Rust crate. `pnpm core:wasm` has to have run first.
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { beforeAll, describe, expect, it } from "vitest";

import { analyze, init, reconstruct, version, type Stage } from "../src/index.ts";

const repoRoot = new URL("../../../", import.meta.url);
const wasmPath = fileURLToPath(new URL("../pkg/mesh2param_wasm_bg.wasm", import.meta.url));

async function sample(slug: string, mesh: string): Promise<Uint8Array> {
  const path = fileURLToPath(new URL(`samples/real/${slug}/${mesh}`, repoRoot));
  return new Uint8Array(await readFile(path));
}

beforeAll(async () => {
  await init(await readFile(wasmPath));
});

describe("the packaged reconstruction core", () => {
  it("reports its own version and the kernel revision behind it", () => {
    expect(version()).toMatch(/^\d+\.\d+\.\d+ \(remus [0-9a-f]{7,40}\)$/);
  });

  it("analyzes a mesh without reconstructing it", async () => {
    const stats = analyze(await sample("dovetail-slide-block", "mesh-coarse.stl"));
    expect(stats.triangles).toBeGreaterThan(0);
    expect(stats.vertices).toBeGreaterThan(0);
    expect(stats.vertices).toBeLessThan(stats.triangles * 3);
    expect(stats.watertight).toBe(true);
    expect(stats.edgeManifold).toBe(true);
    expect(stats.nonManifoldEdges).toBe(0);
    expect(stats.bbox.max[0]).toBeGreaterThan(stats.bbox.min[0]);
  });

  it("refuses a mesh over the triangle budget as a BudgetError", async () => {
    const bytes = await sample("dovetail-slide-block", "mesh-coarse.stl");
    expect(() => reconstruct(bytes, "stl", { triangleBudget: 4 })).toThrowError(
      expect.objectContaining({ name: "BudgetError" }),
    );
  });

  it("refuses an unknown container", async () => {
    const bytes = await sample("dovetail-slide-block", "mesh-coarse.stl");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(() => reconstruct(bytes, "step" as any)).toThrowError(/unsupported mesh format/);
  });

  // `hammer-holder/mesh-export.stl` is the 70k-triangle export of the same
  // part. It reconstructs correctly but takes about eight minutes in Node —
  // almost all of it in verification, whose grid queries run over a 47k-face
  // tessellation — so the fast mesh of the same part is what CI runs. See
  // README.md, "Measured".
  for (const [slug, mesh] of [
    ["dovetail-slide-block", "mesh-coarse.stl"],
    ["hammer-holder", "mesh-coarse.stl"],
  ] as const) {
    it(`reconstructs ${slug}/${mesh} to an analytic or mixed solid`, async () => {
      const bytes = await sample(slug, mesh);
      const seen: Array<[Stage, number]> = [];

      const started = performance.now();
      const result = reconstruct(bytes, "stl", {}, (stage, fraction) => {
        seen.push([stage, fraction]);
      });
      const elapsed = performance.now() - started;

      expect(["analytic", "mixed"]).toContain(result.tier);
      expect(result.valid).toBe(true);
      expect(result.facesFinal).toBeGreaterThan(0);
      expect(result.inventory.plane).toBeGreaterThan(0);
      expect(result.unknownAreaFraction).toBeLessThan(1);

      const header = new TextDecoder().decode(result.step.subarray(0, 13));
      expect(header).toBe("ISO-10303-21;");
      expect(result.stepBytes).toBe(result.step.length);

      expect(new TextDecoder().decode(result.glb.subarray(0, 4))).toBe("glTF");
      expect(result.glb.length).toBeGreaterThan(1000);

      // The run is finished exactly when step reaches 1.
      expect(seen.at(-1)).toEqual(["step", 1]);
      expect(seen.map(([stage]) => stage)).toContain("segment");
      expect(seen.every(([, fraction]) => fraction >= 0 && fraction <= 1)).toBe(true);

      expect(result.timings.segmentMs).toBeGreaterThan(0);
      expect(elapsed).toBeLessThan(30_000);
    });
  }
});
