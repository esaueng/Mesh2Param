import type { BrowserEdgeLines, BrowserMesh } from "./geometry/types";

function align4(value: number): number {
  return (value + 3) & ~3;
}

function minMax(positions: Float32Array): { min: [number, number, number]; max: [number, number, number] } {
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[index + axis]!;
      if (axis === 0) { min[0] = Math.min(min[0], value); max[0] = Math.max(max[0], value); }
      else if (axis === 1) { min[1] = Math.min(min[1], value); max[1] = Math.max(max[1], value); }
      else { min[2] = Math.min(min[2], value); max[2] = Math.max(max[2], value); }
    }
  }
  return { min, max };
}

export function meshToGlb(mesh: BrowserMesh, edgeLines?: BrowserEdgeLines): Blob {
  const hasEdges = edgeLines !== undefined
    && edgeLines.positions.length >= 6
    && edgeLines.indices.length >= 2;
  const positionLength = mesh.positions.byteLength;
  const normalOffset = align4(positionLength);
  const indexOffset = align4(normalOffset + mesh.normals.byteLength);
  const edgePositionOffset = align4(indexOffset + mesh.indices.byteLength);
  const edgeIndexOffset = align4(
    edgePositionOffset + (hasEdges ? edgeLines.positions.byteLength : 0),
  );
  const binaryLength = align4(
    edgeIndexOffset + (hasEdges ? edgeLines.indices.byteLength : 0),
  );
  const binary = new Uint8Array(binaryLength);
  binary.set(new Uint8Array(mesh.positions.buffer, mesh.positions.byteOffset, mesh.positions.byteLength), 0);
  binary.set(new Uint8Array(mesh.normals.buffer, mesh.normals.byteOffset, mesh.normals.byteLength), normalOffset);
  binary.set(new Uint8Array(mesh.indices.buffer, mesh.indices.byteOffset, mesh.indices.byteLength), indexOffset);
  if (hasEdges) {
    binary.set(
      new Uint8Array(
        edgeLines.positions.buffer,
        edgeLines.positions.byteOffset,
        edgeLines.positions.byteLength,
      ),
      edgePositionOffset,
    );
    binary.set(
      new Uint8Array(
        edgeLines.indices.buffer,
        edgeLines.indices.byteOffset,
        edgeLines.indices.byteLength,
      ),
      edgeIndexOffset,
    );
  }
  const bounds = minMax(mesh.positions);
  const edgeBounds = hasEdges ? minMax(edgeLines.positions) : null;
  const bufferViews = [
    { buffer: 0, byteOffset: 0, byteLength: positionLength, target: 34962 },
    { buffer: 0, byteOffset: normalOffset, byteLength: mesh.normals.byteLength, target: 34962 },
    { buffer: 0, byteOffset: indexOffset, byteLength: mesh.indices.byteLength, target: 34963 },
    ...(hasEdges ? [
      {
        buffer: 0,
        byteOffset: edgePositionOffset,
        byteLength: edgeLines.positions.byteLength,
        target: 34962,
      },
      {
        buffer: 0,
        byteOffset: edgeIndexOffset,
        byteLength: edgeLines.indices.byteLength,
        target: 34963,
      },
    ] : []),
  ];
  const accessors = [
    { bufferView: 0, componentType: 5126, count: mesh.vertexCount, type: "VEC3", min: bounds.min, max: bounds.max },
    { bufferView: 1, componentType: 5126, count: mesh.vertexCount, type: "VEC3" },
    { bufferView: 2, componentType: 5125, count: mesh.indices.length, type: "SCALAR" },
    ...(hasEdges ? [
      {
        bufferView: 3,
        componentType: 5126,
        count: edgeLines.positions.length / 3,
        type: "VEC3",
        min: edgeBounds!.min,
        max: edgeBounds!.max,
      },
      {
        bufferView: 4,
        componentType: 5125,
        count: edgeLines.indices.length,
        type: "SCALAR",
        min: [0],
        max: [edgeLines.positions.length / 3 - 1],
      },
    ] : []),
  ];
  const primitives = [
    { attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, material: 0 },
    ...(hasEdges ? [{
      attributes: { POSITION: 3 },
      indices: 4,
      material: 1,
      mode: 1,
      extras: { mesh2paramAnalyticEdges: true },
    }] : []),
  ];
  const document = {
    asset: { version: "2.0", generator: "Mesh2Param browser OCCT" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, name: "Reconstructed solid" }],
    meshes: [{ primitives }],
    materials: [
      { name: "Reconstructed", pbrMetallicRoughness: { baseColorFactor: [0.2, 0.58, 0.95, 1], metallicFactor: 0.1, roughnessFactor: 0.42 } },
      ...(hasEdges ? [{
        name: "Analytic CAD edges",
        pbrMetallicRoughness: {
          baseColorFactor: [0.02, 0.03, 0.04, 1],
          metallicFactor: 0,
          roughnessFactor: 1,
        },
      }] : []),
    ],
    buffers: [{ byteLength: binaryLength }],
    bufferViews,
    accessors,
  };
  const encoded = new TextEncoder().encode(JSON.stringify(document));
  const jsonLength = align4(encoded.byteLength);
  const totalLength = 12 + 8 + jsonLength + 8 + binaryLength;
  const output = new ArrayBuffer(totalLength);
  const view = new DataView(output);
  const bytes = new Uint8Array(output);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, totalLength, true);
  view.setUint32(12, jsonLength, true);
  view.setUint32(16, 0x4e4f534a, true);
  bytes.fill(0x20, 20, 20 + jsonLength);
  bytes.set(encoded, 20);
  const binaryHeader = 20 + jsonLength;
  view.setUint32(binaryHeader, binaryLength, true);
  view.setUint32(binaryHeader + 4, 0x004e4942, true);
  bytes.set(binary, binaryHeader + 8);
  return new Blob([output], { type: "model/gltf-binary" });
}
