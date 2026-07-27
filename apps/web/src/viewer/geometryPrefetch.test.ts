import { describe, expect, it } from "vitest";
import { geometryNamesForMode, geometryToWarm } from "./geometryPrefetch";

const available = (...names: string[]) => new Set(names);

describe("geometryNamesForMode", () => {
  it("maps a single-layer mode to its artifact", () => {
    expect(geometryNamesForMode("reconstructed")).toEqual(["reconstructed.glb"]);
  });

  it("maps overlay to both layers it draws", () => {
    expect(geometryNamesForMode("overlay")).toEqual(["source.glb", "reconstructed.glb"]);
  });
});

describe("geometryToWarm", () => {
  it("warms the preferred mode when its artifact exists", () => {
    expect(geometryToWarm("reconstructed", available("source.glb", "reconstructed.glb")))
      .toEqual(["reconstructed.glb"]);
  });

  it("follows the viewport's fallback order when the preferred mode has nothing to draw", () => {
    // "residual" is unavailable, and the fallback order reaches "source" first.
    expect(geometryToWarm("residual", available("source.glb", "reconstructed.glb")))
      .toEqual(["source.glb"]);
  });

  it("warms both overlay layers only when both are present", () => {
    expect(geometryToWarm("overlay", available("source.glb", "reconstructed.glb")))
      .toEqual(["source.glb", "reconstructed.glb"]);
  });

  it("falls back rather than half-warming an overlay", () => {
    expect(geometryToWarm("overlay", available("reconstructed.glb")))
      .toEqual(["reconstructed.glb"]);
  });

  it("warms nothing when the project has no geometry yet", () => {
    expect(geometryToWarm("reconstructed", available("analysis.json"))).toEqual([]);
  });
});
