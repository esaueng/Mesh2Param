import { describe, expect, it } from "vitest";

import type { BrowserEdgeLines, BrowserMesh } from "./geometry/types";
import { meshToGlb } from "./glb";

const triangle: BrowserMesh = {
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  vertexCount: 3,
  triangleCount: 1,
};

const exactEdges: BrowserEdgeLines = {
  positions: new Float32Array([0, 0, 0, 0.5, 0.5, 0, 1, 0, 0]),
  indices: new Uint32Array([0, 1, 1, 2]),
  segmentCount: 2,
};

async function glbDocument(blob: Blob) {
  const payload = await blob.arrayBuffer();
  const view = new DataView(payload);
  expect(view.getUint32(0, true)).toBe(0x46546c67);
  const jsonLength = view.getUint32(12, true);
  return JSON.parse(
    new TextDecoder().decode(new Uint8Array(payload, 20, jsonLength)).trim(),
  ) as {
    accessors: Array<{ count: number }>;
    meshes: Array<{ primitives: Array<{ mode?: number; extras?: Record<string, boolean> }> }>;
  };
}

describe("browser GLB display geometry", () => {
  it("embeds exact sampled CAD edges as a separate GL LINES primitive", async () => {
    const document = await glbDocument(meshToGlb(triangle, exactEdges));
    const primitives = document.meshes[0]!.primitives;

    expect(primitives).toHaveLength(2);
    expect(primitives[0]!.mode ?? 4).toBe(4);
    expect(primitives[1]).toMatchObject({
      mode: 1,
      extras: { mesh2paramAnalyticEdges: true },
    });
    expect(document.accessors[4]!.count).toBe(exactEdges.indices.length);
  });

  it("keeps source and faceted mesh GLBs free of synthetic analytic edges", async () => {
    const document = await glbDocument(meshToGlb(triangle));

    expect(document.meshes[0]!.primitives).toHaveLength(1);
    expect(document.accessors).toHaveLength(3);
  });
});
