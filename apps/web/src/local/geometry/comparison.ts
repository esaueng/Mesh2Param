import { BufferAttribute, BufferGeometry, Vector3 } from "three";
import { MeshBVH } from "three-mesh-bvh";

import type { BrowserTriangleMesh } from "./mesh";
import type { BrowserComparisonReport, BrowserMesh } from "./types";

interface SampleMesh {
  geometry: BufferGeometry;
  bvh: MeshBVH;
  areas: Float64Array;
  cumulativeAreas: Float64Array;
  totalArea: number;
  triangleCount: number;
}

interface SurfaceSample {
  point: Vector3;
  normal: Vector3;
}

function createSampleMesh(positions: ArrayLike<number>, indices: ArrayLike<number>): SampleMesh {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(Float32Array.from(positions), 3));
  geometry.setIndex(new BufferAttribute(Uint32Array.from(indices), 1));
  const triangleCount = indices.length / 3;
  const areas = new Float64Array(triangleCount);
  const cumulativeAreas = new Float64Array(triangleCount);
  const position = geometry.getAttribute("position");
  const index = geometry.getIndex()!;
  const a = new Vector3(); const b = new Vector3(); const c = new Vector3();
  let totalArea = 0;
  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    a.fromBufferAttribute(position, index.getX(triangle * 3));
    b.fromBufferAttribute(position, index.getX(triangle * 3 + 1));
    c.fromBufferAttribute(position, index.getX(triangle * 3 + 2));
    const area = b.clone().sub(a).cross(c.clone().sub(a)).length() / 2;
    if (!Number.isFinite(area) || area <= 1e-18) throw new Error(`Comparison triangle ${triangle} is degenerate`);
    totalArea += area;
    areas[triangle] = area;
    cumulativeAreas[triangle] = totalArea;
  }
  return { geometry, bvh: new MeshBVH(geometry, { indirect: true }), areas, cumulativeAreas, totalArea, triangleCount };
}

function xorshift(seedValue: number): () => number {
  let seed = seedValue >>> 0 || 0x4d325006;
  return () => {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return (seed >>> 0) / 0x1_0000_0000;
  };
}

function triangleForArea(mesh: SampleMesh, area: number): number {
  let lower = 0; let upper = mesh.cumulativeAreas.length - 1;
  while (lower < upper) {
    const middle = Math.floor((lower + upper) / 2);
    if (mesh.cumulativeAreas[middle]! >= area) upper = middle;
    else lower = middle + 1;
  }
  return lower;
}

function triangleNormal(mesh: SampleMesh, triangle: number): Vector3 {
  const position = mesh.geometry.getAttribute("position");
  const index = mesh.geometry.getIndex()!;
  const a = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3));
  const b = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3 + 1));
  const c = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3 + 2));
  return b.sub(a).cross(c.sub(a)).normalize();
}

function sampleSurface(mesh: SampleMesh, random: () => number): SurfaceSample {
  const triangle = triangleForArea(mesh, random() * mesh.totalArea);
  const position = mesh.geometry.getAttribute("position");
  const index = mesh.geometry.getIndex()!;
  const a = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3));
  const b = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3 + 1));
  const c = new Vector3().fromBufferAttribute(position, index.getX(triangle * 3 + 2));
  const root = Math.sqrt(random());
  const left = 1 - root;
  const right = root * (1 - random());
  const last = 1 - left - right;
  return {
    point: a.multiplyScalar(left).addScaledVector(b, right).addScaledVector(c, last),
    normal: triangleNormal(mesh, triangle),
  };
}

function percentile(sorted: readonly number[], fraction: number): number {
  if (sorted.length === 0) return 0;
  const position = Math.max(0, Math.min(sorted.length - 1, fraction * (sorted.length - 1)));
  const lower = Math.floor(position); const upper = Math.ceil(position);
  return sorted[lower]! + (sorted[upper]! - sorted[lower]!) * (position - lower);
}

function measureDirection(
  source: SampleMesh,
  target: SampleMesh,
  sampleCount: number,
  random: () => number,
): { distances: number[]; normalAgreements: number[]; normalAngles: number[] } {
  const distances: number[] = [];
  const normalAgreements: number[] = [];
  const normalAngles: number[] = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const sample = sampleSurface(source, random);
    const hit = target.bvh.closestPointToPoint(sample.point);
    if (hit === null || hit.faceIndex === undefined) throw new Error("BVH comparison did not return a closest face");
    const targetNormal = triangleNormal(target, hit.faceIndex);
    const agreement = Math.max(-1, Math.min(1, sample.normal.dot(targetNormal)));
    distances.push(hit.distance);
    normalAgreements.push(agreement);
    normalAngles.push(Math.acos(agreement) * 180 / Math.PI);
  }
  return { distances, normalAgreements, normalAngles };
}

export function compareMeshes(
  source: BrowserTriangleMesh,
  result: BrowserMesh,
  resultVolume: number,
  tolerance: number,
  seed: number,
  sampleCountEachDirection = 1500,
): BrowserComparisonReport {
  const sourceMesh = createSampleMesh(source.vertices, source.faces);
  const resultMesh = createSampleMesh(result.positions, result.indices);
  try {
    const random = xorshift(seed);
    const forward = measureDirection(sourceMesh, resultMesh, sampleCountEachDirection, random);
    const reverse = measureDirection(resultMesh, sourceMesh, sampleCountEachDirection, random);
    const distances = [...forward.distances, ...reverse.distances].sort((left, right) => left - right);
    const agreements = [...forward.normalAgreements, ...reverse.normalAgreements];
    const angles = [...forward.normalAngles, ...reverse.normalAngles].sort((left, right) => left - right);
    return {
      sampleCountEachDirection,
      distance: {
        rms: Math.sqrt(distances.reduce((sum, value) => sum + value * value, 0) / distances.length),
        median: percentile(distances, 0.5),
        p95: percentile(distances, 0.95),
        p99: percentile(distances, 0.99),
        maximum: distances.at(-1) ?? 0,
      },
      normals: {
        meanAgreement: agreements.reduce((sum, value) => sum + value, 0) / agreements.length,
        p95AngleDeg: percentile(angles, 0.95),
      },
      relativeVolumeDelta: source.volume > 1e-15 ? Math.abs(resultVolume - source.volume) / source.volume : null,
      tolerance,
      toleranceSurfaceCoverage: distances.filter((distance) => distance <= tolerance).length / distances.length,
    };
  } finally {
    sourceMesh.geometry.dispose();
    resultMesh.geometry.dispose();
  }
}
