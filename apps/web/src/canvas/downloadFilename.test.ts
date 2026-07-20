import { describe, expect, it } from "vitest";
import { artifactDownloadName, stepDownloadName, suffixFromBytes } from "./downloadFilename";

describe("STEP download filenames", () => {
  it("appends an exact five-character suffix after the latest project name", () => {
    expect(stepDownloadName("Merged QA Bracket.step", "model.step", "k7m2q"))
      .toBe("Merged QA Bracket-k7m2q.step");
    expect(stepDownloadName("fixture/plate", "model.stp", "a1b2c"))
      .toBe("fixture-plate-a1b2c.stp");
  });

  it("maps random bytes to five lowercase alphanumeric characters", () => {
    expect(suffixFromBytes(new Uint8Array([0, 25, 26, 35, 36]))).toBe("az09a");
    expect(() => suffixFromBytes(new Uint8Array(4))).toThrow(/at least 5 random bytes/);
  });

  it("rejects malformed supplied suffixes", () => {
    expect(() => stepDownloadName("model", "model.step", "ABC12")).toThrow(/exactly five/);
    expect(() => stepDownloadName("model", "model.step", "abcd")).toThrow(/exactly five/);
  });

  it("preserves non-STEP artifact extensions", () => {
    expect(artifactDownloadName("Bracket.step", "reconstructed.glb", "g1b2c"))
      .toBe("Bracket-g1b2c.glb");
  });
});
