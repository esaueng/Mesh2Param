import type { BrowserCadResult, BrowserMeshDiagnostics } from "./types";

const MAX_BROWSER_TRIANGLES = 2_000_000;

interface EdgeUse {
  left: number;
  right: number;
  count: number;
  directionBalance: number;
  firstFace: number;
}

function find(parent: Int32Array, value: number): number {
  let root = value;
  while (parent[root] !== root) root = parent[root]!;
  while (parent[value] !== value) {
    const next = parent[value]!;
    parent[value] = root;
    value = next;
  }
  return root;
}

function union(parent: Int32Array, left: number, right: number): void {
  const leftRoot = find(parent, left);
  const rightRoot = find(parent, right);
  if (leftRoot !== rightRoot) parent[Math.max(leftRoot, rightRoot)] = Math.min(leftRoot, rightRoot);
}

function binaryPositions(bytes: ArrayBuffer): Float32Array | null {
  if (bytes.byteLength < 84) return null;
  const view = new DataView(bytes);
  const triangleCount = view.getUint32(80, true);
  if (84 + triangleCount * 50 !== bytes.byteLength) return null;
  if (triangleCount === 0 || triangleCount > MAX_BROWSER_TRIANGLES) {
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
  const triangleCount = values.length / 9;
  if (triangleCount > MAX_BROWSER_TRIANGLES) {
    throw new Error(`STL triangle count ${triangleCount.toLocaleString()} exceeds the browser limit`);
  }
  return Float32Array.from(values);
}

function vertexKey(x: number, y: number, z: number): string {
  return `${x},${y},${z}`;
}

function topologyDiagnostics(weldedFaces: Uint32Array, weldedVertexCount: number): BrowserMeshDiagnostics {
  const triangleCount = weldedFaces.length / 3;
  const faceParent = new Int32Array(triangleCount);
  for (let face = 0; face < triangleCount; face += 1) faceParent[face] = face;
  const edges = new Map<string, EdgeUse>();
  const faces = new Map<string, number>();
  let duplicateFaceCount = 0;

  for (let face = 0; face < triangleCount; face += 1) {
    const a = weldedFaces[face * 3]!;
    const b = weldedFaces[face * 3 + 1]!;
    const c = weldedFaces[face * 3 + 2]!;
    const canonical = [a, b, c].sort((left, right) => left - right).join(",");
    if (faces.has(canonical)) duplicateFaceCount += 1;
    else faces.set(canonical, face);
    for (const [start, end] of [[a, b], [b, c], [c, a]] as const) {
      if (start === end) continue;
      const left = Math.min(start, end);
      const right = Math.max(start, end);
      const key = `${left}:${right}`;
      const previous = edges.get(key);
      if (previous === undefined) {
        edges.set(key, { left, right, count: 1, directionBalance: start < end ? 1 : -1, firstFace: face });
      } else {
        previous.count += 1;
        previous.directionBalance += start < end ? 1 : -1;
        union(faceParent, previous.firstFace, face);
      }
    }
  }

  let openBoundaryEdgeCount = 0;
  let nonManifoldEdgeCount = 0;
  let windingConsistent = true;
  const boundaryParent = new Int32Array(weldedVertexCount);
  const boundaryVertices = new Set<number>();
  for (let vertex = 0; vertex < weldedVertexCount; vertex += 1) boundaryParent[vertex] = vertex;
  for (const edge of edges.values()) {
    if (edge.count === 1) {
      openBoundaryEdgeCount += 1;
      boundaryVertices.add(edge.left);
      boundaryVertices.add(edge.right);
      union(boundaryParent, edge.left, edge.right);
    } else if (edge.count > 2) {
      nonManifoldEdgeCount += 1;
    }
    if (edge.count === 2 && edge.directionBalance !== 0) windingConsistent = false;
  }
  const connectedComponentCount = new Set(
    Array.from({ length: triangleCount }, (_value, face) => find(faceParent, face)),
  ).size;
  const openBoundaryCount = new Set(
    Array.from(boundaryVertices, (vertex) => find(boundaryParent, vertex)),
  ).size;
  return {
    rawVertexCount: weldedFaces.length,
    weldedVertexCount,
    duplicateVertexCount: weldedFaces.length - weldedVertexCount,
    connectedComponentCount,
    degenerateTriangleCount: 0,
    duplicateFaceCount,
    nonManifoldEdgeCount,
    openBoundaryEdgeCount,
    openBoundaryCount,
    watertight: edges.size > 0 && openBoundaryEdgeCount === 0 && nonManifoldEdgeCount === 0,
    windingConsistent,
  };
}

/** Analyze and render STL triangles directly, without importing them into OCCT and tessellating them again. */
export function analyzeStl(bytes: ArrayBuffer): BrowserCadResult {
  const positions = binaryPositions(bytes) ?? asciiPositions(bytes);
  const triangleCount = positions.length / 9;
  const vertexCount = positions.length / 3;
  const normals = new Float32Array(positions.length);
  const indices = new Uint32Array(vertexCount);
  const weldedFaces = new Uint32Array(vertexCount);
  const welded = new Map<string, number>();
  const lower: [number, number, number] = [Infinity, Infinity, Infinity];
  const upper: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  let surfaceArea = 0;
  let signedVolume = 0;
  let degenerateTriangleCount = 0;

  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    const base = triangle * 9;
    const ax = positions[base]!;
    const ay = positions[base + 1]!;
    const az = positions[base + 2]!;
    const bx = positions[base + 3]!;
    const by = positions[base + 4]!;
    const bz = positions[base + 5]!;
    const cx = positions[base + 6]!;
    const cy = positions[base + 7]!;
    const cz = positions[base + 8]!;
    if (![ax, ay, az, bx, by, bz, cx, cy, cz].every(Number.isFinite)) {
      throw new Error("STL contains a non-finite vertex coordinate");
    }
    const abx = bx - ax;
    const aby = by - ay;
    const abz = bz - az;
    const acx = cx - ax;
    const acy = cy - ay;
    const acz = cz - az;
    const nx = aby * acz - abz * acy;
    const ny = abz * acx - abx * acz;
    const nz = abx * acy - aby * acx;
    const doubledArea = Math.hypot(nx, ny, nz);
    if (doubledArea <= 1e-18) degenerateTriangleCount += 1;
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
      const x = positions[position]!;
      const y = positions[position + 1]!;
      const z = positions[position + 2]!;
      lower[0] = Math.min(lower[0], x); lower[1] = Math.min(lower[1], y); lower[2] = Math.min(lower[2], z);
      upper[0] = Math.max(upper[0], x); upper[1] = Math.max(upper[1], y); upper[2] = Math.max(upper[2], z);
      const key = vertexKey(x, y, z);
      let weldedIndex = welded.get(key);
      if (weldedIndex === undefined) {
        weldedIndex = welded.size;
        welded.set(key, weldedIndex);
      }
      weldedFaces[index] = weldedIndex;
    }
  }

  const diagnostics = topologyDiagnostics(weldedFaces, welded.size);
  diagnostics.degenerateTriangleCount = degenerateTriangleCount;
  const valid = degenerateTriangleCount === 0
    && diagnostics.duplicateFaceCount === 0
    && diagnostics.nonManifoldEdgeCount === 0
    && diagnostics.windingConsistent;
  return {
    step: "",
    mesh: { positions, normals, indices, vertexCount, triangleCount },
    valid,
    solid: diagnostics.watertight,
    stepReimportValid: false,
    volume: Math.abs(signedVolume),
    surfaceArea,
    bounds: [lower, upper],
    featureCount: 1,
    diagnostics,
  };
}
