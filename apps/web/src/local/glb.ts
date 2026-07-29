import type { BrowserEdgeLines, BrowserMesh } from "./geometry/types";

type IndexArray = Uint8Array | Uint16Array | Uint32Array;

interface PackedIndices {
  values: IndexArray;
  componentType: 5121 | 5123 | 5125;
}

interface PositionQuantization {
  origin: [number, number, number];
  scale: number;
}

interface PackedPositions {
  values: Float32Array | Uint16Array;
  min: [number, number, number];
  max: [number, number, number];
}

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

function compactIndices(indices: Uint32Array): PackedIndices {
  let maximum = 0;
  for (const index of indices) maximum = Math.max(maximum, index);
  if (maximum <= 0xff) return { values: new Uint8Array(indices), componentType: 5121 };
  if (maximum <= 0xffff) return { values: new Uint16Array(indices), componentType: 5123 };
  return { values: indices, componentType: 5125 };
}

function positionQuantization(
  surface: Float32Array,
  edges: Float32Array,
): PositionQuantization {
  const bounds = minMax(surface);
  const edgeBounds = minMax(edges);
  const origin: [number, number, number] = [
    Math.min(bounds.min[0], edgeBounds.min[0]),
    Math.min(bounds.min[1], edgeBounds.min[1]),
    Math.min(bounds.min[2], edgeBounds.min[2]),
  ];
  const maximum: [number, number, number] = [
    Math.max(bounds.max[0], edgeBounds.max[0]),
    Math.max(bounds.max[1], edgeBounds.max[1]),
    Math.max(bounds.max[2], edgeBounds.max[2]),
  ];
  const scale = Math.max(
    maximum[0] - origin[0],
    maximum[1] - origin[1],
    maximum[2] - origin[2],
  );
  if (!Number.isFinite(scale) || scale <= 0) {
    throw new Error("Display GLB positions must span a finite positive range");
  }
  return { origin, scale };
}

function quantizePositions(
  positions: Float32Array,
  quantization: PositionQuantization,
): PackedPositions {
  // KHR_mesh_quantization requires each VEC3 element to start on a four-byte
  // boundary, so the fourth uint16 is deterministic padding.
  const values = new Uint16Array(positions.length / 3 * 4);
  const min: [number, number, number] = [0xffff, 0xffff, 0xffff];
  const max: [number, number, number] = [0, 0, 0];
  for (let vertex = 0; vertex < positions.length / 3; vertex += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      const source = positions[vertex * 3 + axis]!;
      const value = Math.min(
        0xffff,
        Math.max(0, Math.round((source - quantization.origin[axis]!) / quantization.scale * 0xffff)),
      );
      values[vertex * 4 + axis] = value;
      min[axis] = Math.min(min[axis]!, value);
      max[axis] = Math.max(max[axis]!, value);
    }
  }
  return { values, min, max };
}

function quantizeNormals(normals: Float32Array): Int8Array {
  // Signed-byte normals keep a four-byte stride. ArtifactLayer recomputes the
  // display normals, while standalone GLB consumers retain smooth PBR normals.
  const values = new Int8Array(normals.length / 3 * 4);
  for (let vertex = 0; vertex < normals.length / 3; vertex += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      const source = normals[vertex * 3 + axis]!;
      values[vertex * 4 + axis] = Math.round(Math.max(-1, Math.min(1, source)) * 127);
    }
  }
  return values;
}

function copyView(target: Uint8Array, source: ArrayBufferView, offset: number): void {
  target.set(new Uint8Array(source.buffer, source.byteOffset, source.byteLength), offset);
}

export function meshToGlb(mesh: BrowserMesh, edgeLines?: BrowserEdgeLines): Blob {
  const hasEdges = edgeLines !== undefined
    && edgeLines.positions.length >= 6
    && edgeLines.indices.length >= 2;
  const quantization = hasEdges
    ? positionQuantization(mesh.positions, edgeLines.positions)
    : null;
  const surfacePositions = quantization === null
    ? { values: mesh.positions, ...minMax(mesh.positions) }
    : quantizePositions(mesh.positions, quantization);
  const surfaceNormals = quantization === null ? mesh.normals : quantizeNormals(mesh.normals);
  const surfaceIndices = quantization === null
    ? { values: mesh.indices, componentType: 5125 as const }
    : compactIndices(mesh.indices);
  const analyticPositions = quantization === null
    ? null
    : quantizePositions(edgeLines!.positions, quantization);
  const analyticIndices = quantization === null ? null : compactIndices(edgeLines!.indices);
  const positionLength = surfacePositions.values.byteLength;
  const normalOffset = align4(positionLength);
  const indexOffset = align4(normalOffset + surfaceNormals.byteLength);
  const edgePositionOffset = align4(indexOffset + surfaceIndices.values.byteLength);
  const edgeIndexOffset = align4(
    edgePositionOffset + (analyticPositions?.values.byteLength ?? 0),
  );
  const binaryLength = align4(
    edgeIndexOffset + (analyticIndices?.values.byteLength ?? 0),
  );
  const binary = new Uint8Array(binaryLength);
  copyView(binary, surfacePositions.values, 0);
  copyView(binary, surfaceNormals, normalOffset);
  copyView(binary, surfaceIndices.values, indexOffset);
  if (analyticPositions !== null && analyticIndices !== null) {
    copyView(binary, analyticPositions.values, edgePositionOffset);
    copyView(binary, analyticIndices.values, edgeIndexOffset);
  }
  const bufferViews = [
    {
      buffer: 0,
      byteOffset: 0,
      byteLength: positionLength,
      target: 34962,
      ...(quantization === null ? {} : { byteStride: 8 }),
    },
    {
      buffer: 0,
      byteOffset: normalOffset,
      byteLength: surfaceNormals.byteLength,
      target: 34962,
      ...(quantization === null ? {} : { byteStride: 4 }),
    },
    {
      buffer: 0,
      byteOffset: indexOffset,
      byteLength: surfaceIndices.values.byteLength,
      target: 34963,
    },
    ...(hasEdges ? [
      {
        buffer: 0,
        byteOffset: edgePositionOffset,
        byteLength: analyticPositions!.values.byteLength,
        target: 34962,
        byteStride: 8,
      },
      {
        buffer: 0,
        byteOffset: edgeIndexOffset,
        byteLength: analyticIndices!.values.byteLength,
        target: 34963,
      },
    ] : []),
  ];
  const accessors = [
    {
      bufferView: 0,
      componentType: quantization === null ? 5126 : 5123,
      count: mesh.vertexCount,
      type: "VEC3",
      min: surfacePositions.min,
      max: surfacePositions.max,
      ...(quantization === null ? {} : { normalized: true }),
    },
    {
      bufferView: 1,
      componentType: quantization === null ? 5126 : 5120,
      count: mesh.vertexCount,
      type: "VEC3",
      ...(quantization === null ? {} : { normalized: true }),
    },
    {
      bufferView: 2,
      componentType: surfaceIndices.componentType,
      count: mesh.indices.length,
      type: "SCALAR",
    },
    ...(hasEdges ? [
      {
        bufferView: 3,
        componentType: 5123,
        count: edgeLines.positions.length / 3,
        type: "VEC3",
        min: analyticPositions!.min,
        max: analyticPositions!.max,
        normalized: true,
      },
      {
        bufferView: 4,
        componentType: analyticIndices!.componentType,
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
    ...(quantization === null ? {} : {
      extensionsRequired: ["KHR_mesh_quantization"],
      extensionsUsed: ["KHR_mesh_quantization"],
    }),
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{
      mesh: 0,
      name: "Reconstructed solid",
      ...(quantization === null ? {} : {
        scale: [quantization.scale, quantization.scale, quantization.scale],
        translation: quantization.origin,
      }),
    }],
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
