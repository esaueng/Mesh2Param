import { analyzeStl } from "./stl";

export interface BrowserTriangleMesh {
  vertices: Float64Array;
  faces: Uint32Array;
  faceNormals: Float64Array;
  faceAreas: Float64Array;
  faceCenters: Float64Array;
  bounds: [[number, number, number], [number, number, number]];
  volume: number;
  surfaceArea: number;
  triangleCount: number;
  vertexCount: number;
}

function coordinateKey(x: number, y: number, z: number, tolerance: number): string {
  return `${Math.round(x / tolerance)}:${Math.round(y / tolerance)}:${Math.round(z / tolerance)}`;
}

export function triangleMeshFromStl(
  bytes: ArrayBuffer,
  scaleFactor: number,
  tolerance: number,
): BrowserTriangleMesh {
  if (!Number.isFinite(scaleFactor) || scaleFactor <= 0) throw new Error("Source scale factor must be finite and positive");
  const analyzed = analyzeStl(bytes);
  if (!analyzed.valid || !analyzed.solid) throw new Error("Parametric reconstruction requires a valid watertight STL");
  const raw = analyzed.mesh.positions;
  const weldTolerance = Math.max(1e-9, tolerance * 1e-4);
  const vertexValues: number[] = [];
  const faces = new Uint32Array(raw.length / 3);
  const lookup = new Map<string, number>();
  for (let index = 0; index < raw.length / 3; index += 1) {
    const x = raw[index * 3]! * scaleFactor;
    const y = raw[index * 3 + 1]! * scaleFactor;
    const z = raw[index * 3 + 2]! * scaleFactor;
    const key = coordinateKey(x, y, z, weldTolerance);
    let vertex = lookup.get(key);
    if (vertex === undefined) {
      vertex = vertexValues.length / 3;
      lookup.set(key, vertex);
      vertexValues.push(x, y, z);
    }
    faces[index] = vertex;
  }
  const vertices = Float64Array.from(vertexValues);
  const triangleCount = faces.length / 3;
  const faceNormals = new Float64Array(triangleCount * 3);
  const faceAreas = new Float64Array(triangleCount);
  const faceCenters = new Float64Array(triangleCount * 3);
  const lower: [number, number, number] = [Infinity, Infinity, Infinity];
  const upper: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (let vertex = 0; vertex < vertices.length / 3; vertex += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      lower[axis] = Math.min(lower[axis]!, vertices[vertex * 3 + axis]!);
      upper[axis] = Math.max(upper[axis]!, vertices[vertex * 3 + axis]!);
    }
  }
  let surfaceArea = 0;
  let signedVolume = 0;
  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    const ia = faces[triangle * 3]! * 3;
    const ib = faces[triangle * 3 + 1]! * 3;
    const ic = faces[triangle * 3 + 2]! * 3;
    const ax = vertices[ia]!; const ay = vertices[ia + 1]!; const az = vertices[ia + 2]!;
    const bx = vertices[ib]!; const by = vertices[ib + 1]!; const bz = vertices[ib + 2]!;
    const cx = vertices[ic]!; const cy = vertices[ic + 1]!; const cz = vertices[ic + 2]!;
    const abx = bx - ax; const aby = by - ay; const abz = bz - az;
    const acx = cx - ax; const acy = cy - ay; const acz = cz - az;
    const nx = aby * acz - abz * acy;
    const ny = abz * acx - abx * acz;
    const nz = abx * acy - aby * acx;
    const doubledArea = Math.hypot(nx, ny, nz);
    if (!Number.isFinite(doubledArea) || doubledArea <= Math.max(1e-18, tolerance * tolerance * 1e-12)) {
      throw new Error(`Source triangle ${triangle} is degenerate at the reconstruction tolerance`);
    }
    const area = doubledArea / 2;
    faceAreas[triangle] = area;
    faceNormals[triangle * 3] = nx / doubledArea;
    faceNormals[triangle * 3 + 1] = ny / doubledArea;
    faceNormals[triangle * 3 + 2] = nz / doubledArea;
    faceCenters[triangle * 3] = (ax + bx + cx) / 3;
    faceCenters[triangle * 3 + 1] = (ay + by + cy) / 3;
    faceCenters[triangle * 3 + 2] = (az + bz + cz) / 3;
    surfaceArea += area;
    signedVolume += (
      ax * (by * cz - bz * cy)
      + ay * (bz * cx - bx * cz)
      + az * (bx * cy - by * cx)
    ) / 6;
  }
  return {
    vertices,
    faces,
    faceNormals,
    faceAreas,
    faceCenters,
    bounds: [lower, upper],
    volume: Math.abs(signedVolume),
    surfaceArea,
    triangleCount,
    vertexCount: vertices.length / 3,
  };
}
