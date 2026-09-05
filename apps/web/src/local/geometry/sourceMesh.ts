import type { BrowserMesh } from "./types";

/**
 * Parse source mesh bytes into a renderable triangle soup.
 *
 * This is a display path, not a geometry engine: the reconstruction core owns
 * every geometric decision, but its `analyze` returns statistics rather than
 * geometry, and the viewer still has to draw the mesh the user opened. Area and
 * signed volume are accumulated in the same pass because they are exact sums
 * over the triangles being read, not estimates.
 *
 * Only STL is parsed here. Other containers the core reads are reconstructed
 * without a source preview rather than given a second, divergent reader.
 */

const MAX_DISPLAY_TRIANGLES = 2_000_000;

export interface ParsedSourceMesh {
  mesh: BrowserMesh;
  bounds: [[number, number, number], [number, number, number]];
  surfaceArea: number;
  /** Divergence-theorem volume. Meaningful only if the mesh is closed. */
  signedVolume: number;
}

function binaryPositions(bytes: ArrayBuffer): Float32Array | null {
  if (bytes.byteLength < 84) return null;
  const view = new DataView(bytes);
  const triangleCount = view.getUint32(80, true);
  if (84 + triangleCount * 50 !== bytes.byteLength) return null;
  if (triangleCount === 0 || triangleCount > MAX_DISPLAY_TRIANGLES) {
    throw new Error(`STL triangle count ${triangleCount.toLocaleString()} is outside the browser limit`);
  }
  const positions = new Float32Array(triangleCount * 9);
  let sourceOffset = 84;
  let targetOffset = 0;
  for (let triangle = 0; triangle < triangleCount; triangle += 1, sourceOffset += 50) {
    for (let coordinate = 0; coordinate < 9; coordinate += 1) {
      positions[targetOffset] = view.getFloat32(sourceOffset + 12 + coordinate * 4, true);
      targetOffset += 1;
    }
  }
  return positions;
}

function asciiPositions(bytes: ArrayBuffer): Float32Array {
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  const values: number[] = [];
  const vertex = /^\s*vertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s*$/gim;
  for (let match = vertex.exec(text); match !== null; match = vertex.exec(text)) {
    values.push(Number(match[1]), Number(match[2]), Number(match[3]));
  }
  if (values.length === 0 || values.length % 9 !== 0) {
    throw new Error("ASCII STL does not contain complete triangular facets");
  }
  if (values.length / 9 > MAX_DISPLAY_TRIANGLES) {
    throw new Error(`STL triangle count ${(values.length / 9).toLocaleString()} exceeds the browser limit`);
  }
  return Float32Array.from(values);
}

export function parseStlForDisplay(bytes: ArrayBuffer): ParsedSourceMesh {
  const positions = binaryPositions(bytes) ?? asciiPositions(bytes);
  const triangleCount = positions.length / 9;
  const vertexCount = positions.length / 3;
  const normals = new Float32Array(positions.length);
  const indices = new Uint32Array(vertexCount);
  const lower: [number, number, number] = [Infinity, Infinity, Infinity];
  const upper: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  let surfaceArea = 0;
  let signedVolume = 0;

  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    const base = triangle * 9;
    const ax = positions[base]!, ay = positions[base + 1]!, az = positions[base + 2]!;
    const bx = positions[base + 3]!, by = positions[base + 4]!, bz = positions[base + 5]!;
    const cx = positions[base + 6]!, cy = positions[base + 7]!, cz = positions[base + 8]!;
    if (![ax, ay, az, bx, by, bz, cx, cy, cz].every(Number.isFinite)) {
      throw new Error("STL contains a non-finite vertex coordinate");
    }
    const nx = (by - ay) * (cz - az) - (bz - az) * (cy - ay);
    const ny = (bz - az) * (cx - ax) - (bx - ax) * (cz - az);
    const nz = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    const doubledArea = Math.hypot(nx, ny, nz);
    const inverseLength = doubledArea > 0 ? 1 / doubledArea : 0;
    surfaceArea += doubledArea / 2;
    signedVolume += (ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx)) / 6;
    for (let vertex = 0; vertex < 3; vertex += 1) {
      const position = base + vertex * 3;
      const index = triangle * 3 + vertex;
      normals[position] = nx * inverseLength;
      normals[position + 1] = ny * inverseLength;
      normals[position + 2] = nz * inverseLength;
      indices[index] = index;
      const x = positions[position]!, y = positions[position + 1]!, z = positions[position + 2]!;
      lower[0] = Math.min(lower[0], x); lower[1] = Math.min(lower[1], y); lower[2] = Math.min(lower[2], z);
      upper[0] = Math.max(upper[0], x); upper[1] = Math.max(upper[1], y); upper[2] = Math.max(upper[2], z);
    }
  }

  return {
    mesh: { positions, normals, indices, vertexCount, triangleCount },
    bounds: [lower, upper],
    surfaceArea,
    signedVolume: Math.abs(signedVolume),
  };
}
