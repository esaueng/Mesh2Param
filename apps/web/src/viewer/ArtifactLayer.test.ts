import { describe, expect, it } from "vitest";
import { patchForFace, selectedTriangleRanges, type SelectionRange } from "./ArtifactLayer";

const ranges: SelectionRange[] = [
  { triangleStart: 0, triangleEndExclusive: 4, patchId: "patch-a", semanticIds: ["patch-a"] },
  { triangleStart: 4, triangleEndExclusive: 8, patchId: "patch-b", semanticIds: ["patch-b"] },
  { triangleStart: 8, triangleEndExclusive: 10, patchId: "patch-a", semanticIds: ["patch-a"] },
];

describe("selection map lookup", () => {
  it("resolves face indices against the authoritative triangle ranges", () => {
    expect(patchForFace(ranges, 0)).toBe("patch-a");
    expect(patchForFace(ranges, 7)).toBe("patch-b");
    expect(patchForFace(ranges, 10)).toBeNull();
  });

  it("retains every disjoint range for the selected viewport highlight", () => {
    expect(selectedTriangleRanges(ranges, "patch-a")).toHaveLength(2);
    expect(selectedTriangleRanges(ranges, null)).toEqual([]);
  });
});
