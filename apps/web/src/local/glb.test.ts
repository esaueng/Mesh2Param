import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { GLTFLoader, type GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";

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
    accessors: Array<{
      componentType: number;
      count: number;
      normalized?: boolean;
    }>;
    bufferViews: Array<{ byteStride?: number }>;
    extensionsRequired?: string[];
    extensionsUsed?: string[];
    meshes: Array<{
      primitives: Array<{
        attributes: { NORMAL?: number; POSITION: number };
        indices: number;
        mode?: number;
        extras?: Record<string, boolean>;
      }>;
    }>;
    nodes: Array<{ scale?: number[]; translation?: number[] }>;
  };
}

async function loadGlb(blob: Blob): Promise<GLTF> {
  const payload = await blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    new GLTFLoader().parse(payload, "", resolve, reject);
  });
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
    expect(document.extensionsRequired).toEqual(["KHR_mesh_quantization"]);
    expect(document.extensionsUsed).toEqual(["KHR_mesh_quantization"]);
    expect(document.accessors[0]).toMatchObject({ componentType: 5123, normalized: true });
    expect(document.accessors[1]).toMatchObject({ componentType: 5120, normalized: true });
    expect(document.accessors[2]).toMatchObject({ componentType: 5121 });
    expect(document.accessors[3]).toMatchObject({ componentType: 5123, normalized: true });
    expect(document.accessors[4]).toMatchObject({ componentType: 5121 });
    expect(document.bufferViews[0]!.byteStride).toBe(8);
    expect(document.bufferViews[1]!.byteStride).toBe(4);
    expect(document.bufferViews[3]!.byteStride).toBe(8);
    expect(document.nodes[0]).toMatchObject({
      scale: [1, 1, 1],
      translation: [0, 0, 0],
    });
    expect(document.accessors[4]!.count).toBe(exactEdges.indices.length);
  });

  it("loads compact surfaces and analytic lines with their shared transform", async () => {
    const gltf = await loadGlb(meshToGlb(triangle, exactEdges));
    const bounds = new THREE.Box3().setFromObject(gltf.scene);
    const meshes: THREE.Mesh[] = [];
    const lines: THREE.LineSegments[] = [];
    gltf.scene.traverse((child) => {
      if (child instanceof THREE.LineSegments) lines.push(child);
      else if (child instanceof THREE.Mesh) meshes.push(child);
    });

    expect(meshes).toHaveLength(1);
    expect(lines).toHaveLength(1);
    expect(bounds.min.toArray()).toEqual([0, 0, 0]);
    expect(bounds.max.toArray()).toEqual([1, 1, 0]);
    expect(meshes[0]!.geometry.getAttribute("position")).toMatchObject({
      count: 3,
      normalized: true,
    });
    expect(lines[0]!.geometry.getAttribute("position")).toMatchObject({
      count: 3,
      normalized: true,
    });
  });

  it("keeps source and faceted mesh GLBs free of synthetic analytic edges", async () => {
    const document = await glbDocument(meshToGlb(triangle));

    expect(document.meshes[0]!.primitives).toHaveLength(1);
    expect(document.accessors).toHaveLength(3);
    expect(document.extensionsRequired).toBeUndefined();
    expect(document.extensionsUsed).toBeUndefined();
  });
});
