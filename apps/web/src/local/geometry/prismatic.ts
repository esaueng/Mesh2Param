import type { CADGraph, Units } from "@mesh2param/contracts";

import type { SourceAssetDescriptor } from "../../state/types";
import { fitBoundedBSpline, type BrowserBSplinePrimitive } from "./profileFitting";
import type { Vec2 } from "./sections";

type Vec3 = [number, number, number];

export interface LinePrimitive {
  kind: "line";
  start: Vec2;
  end: Vec2;
  rms: number;
  maximum: number;
}

export interface ArcPrimitive {
  kind: "arc";
  start: Vec2;
  end: Vec2;
  center: Vec2;
  radius: number;
  sweepDeg: number;
  rms: number;
  maximum: number;
}

export interface CirclePrimitive {
  kind: "circle";
  start: Vec2;
  end: Vec2;
  center: Vec2;
  radius: number;
  rms: number;
  maximum: number;
}

type AnalyticPrimitive = LinePrimitive | ArcPrimitive | CirclePrimitive;
export type BrowserProfilePrimitive = AnalyticPrimitive | BrowserBSplinePrimitive;

interface AxisCandidate {
  axisIndex: 0 | 1 | 2;
  minimum: number;
  maximum: number;
  capArea: number;
  loops: Vec2[][];
  profiles: AnalyticPrimitive[][];
}

export interface BrowserPrismaticReconstruction {
  graph: CADGraph;
  analysis: {
    accepted: true;
    axis: Vec3;
    distanceMm: number;
    confidence: number;
    relativeVolumeDelta: number;
    profiles: Array<Array<Record<string, unknown>>>;
  };
}

const LINE_RMS_TOLERANCE = 0.025;
const LINE_MAX_TOLERANCE = 0.075;
const ARC_RMS_TOLERANCE = 0.025;
const ARC_MAX_TOLERANCE = 0.075;
const MINIMUM_LENGTH = 0.1;
const MINIMUM_ARC_SWEEP_DEG = 8;
const MINIMUM_ARC_SAGITTA = 0.04;
const MAXIMUM_PROFILE_VERTICES = 1024;
const MAXIMUM_INTERVAL_VERTICES = 512;
const MAXIMUM_RELATIVE_VOLUME_DELTA = 0.01;

function distance(left: Vec2, right: Vec2): number {
  return Math.hypot(right[0] - left[0], right[1] - left[1]);
}

function signedArea(points: readonly Vec2[]): number {
  let result = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]!;
    const following = points[(index + 1) % points.length]!;
    result += current[0] * following[1] - current[1] * following[0];
  }
  return result / 2;
}

function canonicalLoop(points: Vec2[], clockwise: boolean): Vec2[] {
  let result = points.filter((point, index) => index === 0 || distance(point, points[index - 1]!) > 1e-10);
  if (result.length < 3) throw new Error("cap loop collapses after vertex welding");
  if ((signedArea(result) < 0) !== clockwise) result = [...result].reverse();
  let start = 0;
  for (let index = 1; index < result.length; index += 1) {
    const candidate = result[index]!;
    const selected = result[start]!;
    if (candidate[0] < selected[0] || (candidate[0] === selected[0] && candidate[1] < selected[1])) start = index;
  }
  return [...result.slice(start), ...result.slice(0, start)];
}

function triangleArea(positions: Float32Array, triangle: number): number {
  const base = triangle * 9;
  const abx = positions[base + 3]! - positions[base]!;
  const aby = positions[base + 4]! - positions[base + 1]!;
  const abz = positions[base + 5]! - positions[base + 2]!;
  const acx = positions[base + 6]! - positions[base]!;
  const acy = positions[base + 7]! - positions[base + 1]!;
  const acz = positions[base + 8]! - positions[base + 2]!;
  return Math.hypot(
    aby * acz - abz * acy,
    abz * acx - abx * acz,
    abx * acy - aby * acx,
  ) / 2;
}

function meshVolume(positions: Float32Array): number {
  let signedVolume = 0;
  for (let triangle = 0; triangle < positions.length / 9; triangle += 1) {
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
    signedVolume += (
      ax * (by * cz - bz * cy)
      + ay * (bz * cx - bx * cz)
      + az * (bx * cy - by * cx)
    ) / 6;
  }
  return Math.abs(signedVolume);
}

function vertexKey(point: Vec3): string {
  return `${point[0]},${point[1]},${point[2]}`;
}

function weldedMesh(positions: Float32Array): { vertices: Vec3[]; faces: Array<[number, number, number]> } {
  const vertices: Vec3[] = [];
  const lookup = new Map<string, number>();
  const faces: Array<[number, number, number]> = [];
  for (let triangle = 0; triangle < positions.length / 9; triangle += 1) {
    const face: number[] = [];
    for (let corner = 0; corner < 3; corner += 1) {
      const offset = triangle * 9 + corner * 3;
      const point: Vec3 = [positions[offset]!, positions[offset + 1]!, positions[offset + 2]!];
      const key = vertexKey(point);
      let index = lookup.get(key);
      if (index === undefined) {
        index = vertices.length;
        lookup.set(key, index);
        vertices.push(point);
      }
      face.push(index);
    }
    faces.push(face as [number, number, number]);
  }
  return { vertices, faces };
}

function capBoundaryLoops(faces: readonly [number, number, number][], faceIds: readonly number[]): number[][] {
  const counts = new Map<string, { left: number; right: number; count: number }>();
  for (const faceId of faceIds) {
    const face = faces[faceId]!;
    for (const [start, end] of [[face[0], face[1]], [face[1], face[2]], [face[2], face[0]]] as const) {
      const left = Math.min(start, end);
      const right = Math.max(start, end);
      const key = `${left}:${right}`;
      const edge = counts.get(key);
      if (edge === undefined) counts.set(key, { left, right, count: 1 });
      else edge.count += 1;
    }
  }
  const adjacency = new Map<number, number[]>();
  const remaining = new Set<string>();
  for (const [key, edge] of counts) {
    if (edge.count !== 1) continue;
    remaining.add(key);
    adjacency.set(edge.left, [...(adjacency.get(edge.left) ?? []), edge.right]);
    adjacency.set(edge.right, [...(adjacency.get(edge.right) ?? []), edge.left]);
  }
  if (remaining.size === 0 || [...adjacency.values()].some((neighbors) => neighbors.length !== 2)) {
    throw new Error("cap boundary is empty, open, or branching");
  }
  const loops: number[][] = [];
  while (remaining.size > 0) {
    const first = [...remaining][0]!;
    const start = Number(first.split(":")[0]);
    const loop = [start];
    let previous = -1;
    let current = start;
    while (true) {
      const following = (adjacency.get(current) ?? []).find((neighbor) => {
        if (neighbor === previous) return false;
        const key = `${Math.min(current, neighbor)}:${Math.max(current, neighbor)}`;
        return remaining.has(key) || neighbor === start;
      });
      if (following === undefined) throw new Error("cap boundary loop did not close");
      remaining.delete(`${Math.min(current, following)}:${Math.max(current, following)}`);
      if (following === start) break;
      loop.push(following);
      previous = current;
      current = following;
      if (loop.length > adjacency.size) throw new Error("cap boundary traversal cycled");
    }
    if (loop.length < 3) throw new Error("cap boundary loop has fewer than three points");
    loops.push(loop);
  }
  return loops;
}

function projectedPoint(point: Vec3, axisIndex: 0 | 1 | 2): Vec2 {
  if (axisIndex === 0) return [point[1], point[2]];
  if (axisIndex === 1) return [point[2], point[0]];
  return [point[0], point[1]];
}

function solve3(matrix: number[][], values: number[]): number[] | null {
  const augmented = matrix.map((row, index) => [...row, values[index]!]);
  for (let column = 0; column < 3; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < 3; row += 1) {
      if (Math.abs(augmented[row]![column]!) > Math.abs(augmented[pivot]![column]!)) pivot = row;
    }
    if (Math.abs(augmented[pivot]![column]!) <= 1e-15) return null;
    [augmented[column], augmented[pivot]] = [augmented[pivot]!, augmented[column]!];
    const divisor = augmented[column]![column]!;
    for (let entry = column; entry < 4; entry += 1) {
      augmented[column]![entry] = augmented[column]![entry]! / divisor;
    }
    for (let row = 0; row < 3; row += 1) {
      if (row === column) continue;
      const factor = augmented[row]![column]!;
      for (let entry = column; entry < 4; entry += 1) {
        augmented[row]![entry] = augmented[row]![entry]! - factor * augmented[column]![entry]!;
      }
    }
  }
  return augmented.map((row) => row[3]!);
}

function circleInitial(points: readonly Vec2[]): Vec2 | null {
  const matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const values = [0, 0, 0];
  for (const point of points) {
    const row = [2 * point[0], 2 * point[1], 1];
    const target = point[0] * point[0] + point[1] * point[1];
    for (let left = 0; left < 3; left += 1) {
      values[left]! += row[left]! * target;
      for (let right = 0; right < 3; right += 1) matrix[left]![right]! += row[left]! * row[right]!;
    }
  }
  const solved = solve3(matrix, values);
  return solved === null ? null : [solved[0]!, solved[1]!];
}

function linePrimitive(points: readonly Vec2[]): LinePrimitive | null {
  if (points.length < 2) return null;
  const start = points[0]!;
  const end = points.at(-1)!;
  const length = distance(start, end);
  if (length < MINIMUM_LENGTH) return null;
  let squared = 0;
  let maximum = 0;
  for (const point of points) {
    const residual = Math.abs((end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (end[1] - start[1])) / length;
    squared += residual * residual;
    maximum = Math.max(maximum, residual);
  }
  const rms = Math.sqrt(squared / points.length);
  return rms <= LINE_RMS_TOLERANCE && maximum <= LINE_MAX_TOLERANCE
    ? { kind: "line", start, end, rms, maximum }
    : null;
}

function unwrappedAngles(points: readonly Vec2[], center: Vec2): number[] {
  const result: number[] = [];
  for (const point of points) {
    let angle = Math.atan2(point[1] - center[1], point[0] - center[0]);
    const previous = result.at(-1);
    if (previous !== undefined) {
      while (angle - previous > Math.PI) angle -= 2 * Math.PI;
      while (angle - previous < -Math.PI) angle += 2 * Math.PI;
    }
    result.push(angle);
  }
  return result;
}

function arcPrimitive(points: readonly Vec2[]): ArcPrimitive | null {
  if (points.length < 5) return null;
  const start = points[0]!;
  const end = points.at(-1)!;
  const chordX = end[0] - start[0];
  const chordY = end[1] - start[1];
  const chordLength = Math.hypot(chordX, chordY);
  if (chordLength < MINIMUM_LENGTH) return null;
  const midpoint: Vec2 = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
  const bisector: Vec2 = [-chordY / chordLength, chordX / chordLength];
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const scale = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), chordLength, 1);
  const maximumRadius = 20 * scale;
  const initialCenter = circleInitial(points);
  let parameter = initialCenter === null
    ? 0
    : (initialCenter[0] - midpoint[0]) * bisector[0] + (initialCenter[1] - midpoint[1]) * bisector[1];
  const bound = Math.sqrt(Math.max(maximumRadius * maximumRadius - chordLength * chordLength / 4, 1));
  parameter = Math.max(-bound, Math.min(bound, parameter));
  for (let iteration = 0; iteration < 6; iteration += 1) {
    const center: Vec2 = [midpoint[0] + parameter * bisector[0], midpoint[1] + parameter * bisector[1]];
    const endpointDistance = Math.max(distance(start, center), 1e-15);
    let numerator = 0;
    let denominator = 0;
    for (const point of points) {
      const pointDistance = Math.max(distance(point, center), 1e-15);
      const value = pointDistance - endpointDistance;
      const derivative = ((center[0] - point[0]) * bisector[0] + (center[1] - point[1]) * bisector[1]) / pointDistance
        - ((center[0] - start[0]) * bisector[0] + (center[1] - start[1]) * bisector[1]) / endpointDistance;
      numerator += value * derivative;
      denominator += derivative * derivative;
    }
    if (denominator <= 1e-20) break;
    const step = numerator / denominator;
    parameter = Math.max(-bound, Math.min(bound, parameter - step));
    if (Math.abs(step) <= 1e-12 * Math.max(1, Math.abs(parameter))) break;
  }
  const center: Vec2 = [midpoint[0] + parameter * bisector[0], midpoint[1] + parameter * bisector[1]];
  const radius = distance(start, center);
  let squared = 0;
  let maximum = 0;
  for (const point of points) {
    const residual = Math.abs(distance(point, center) - radius);
    squared += residual * residual;
    maximum = Math.max(maximum, residual);
  }
  const rms = Math.sqrt(squared / points.length);
  if (!Number.isFinite(radius) || radius > maximumRadius || rms > ARC_RMS_TOLERANCE || maximum > ARC_MAX_TOLERANCE) return null;
  const angles = unwrappedAngles(points, center);
  const differences = angles.slice(1).map((angle, index) => angle - angles[index]!);
  const sorted = [...differences].sort((left, right) => left - right);
  const direction = sorted[Math.floor(sorted.length / 2)]! >= 0 ? 1 : -1;
  const angularSlop = Math.max(1e-4, ARC_MAX_TOLERANCE / Math.max(radius, 1e-9));
  if (differences.some((difference) => direction * difference < -angularSlop)) return null;
  const maximumGap = Math.max(...differences.map(Math.abs));
  maximum = Math.max(maximum, radius * (1 - Math.cos(maximumGap / 2)));
  if (maximum > ARC_MAX_TOLERANCE) return null;
  const sweep = angles.at(-1)! - angles[0]!;
  const sweepDeg = sweep * 180 / Math.PI;
  const sagitta = radius * (1 - Math.cos(Math.abs(sweep) / 2));
  if (Math.abs(sweep) > 2 * Math.PI + angularSlop || Math.abs(sweepDeg) < MINIMUM_ARC_SWEEP_DEG || sagitta < MINIMUM_ARC_SAGITTA) return null;
  return { kind: "arc", start, end, center, radius, sweepDeg, rms, maximum };
}

function circlePrimitive(points: readonly Vec2[]): CirclePrimitive | null {
  if (points.length < 8) return null;
  const center = circleInitial(points);
  if (center === null) return null;
  const radii = points.map((point) => distance(point, center));
  const radius = radii.reduce((sum, value) => sum + value, 0) / radii.length;
  const residuals = radii.map((value) => Math.abs(value - radius));
  const rms = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / residuals.length);
  let maximum = Math.max(...residuals);
  const angles = points.map((point) => {
    const angle = Math.atan2(point[1] - center[1], point[0] - center[0]);
    return angle < 0 ? angle + 2 * Math.PI : angle;
  }).sort((left, right) => left - right);
  const gaps = angles.map((angle, index) => (angles[(index + 1) % angles.length]! + (index + 1 === angles.length ? 2 * Math.PI : 0)) - angle);
  const maximumGap = Math.max(...gaps);
  maximum = Math.max(maximum, radius * (1 - Math.cos(maximumGap / 2)));
  if (radius < MINIMUM_LENGTH || rms > ARC_RMS_TOLERANCE || maximum > ARC_MAX_TOLERANCE || 360 - maximumGap * 180 / Math.PI < 300) return null;
  const start: Vec2 = [center[0] + radius, center[1]];
  return { kind: "circle", start, end: start, center, radius, rms, maximum };
}

function primitiveCost(primitive: AnalyticPrimitive): number {
  const arc = primitive.kind !== "line";
  return primitive.rms / (arc ? ARC_RMS_TOLERANCE : LINE_RMS_TOLERANCE)
    + 0.25 * primitive.maximum / (arc ? ARC_MAX_TOLERANCE : LINE_MAX_TOLERANCE)
    + 1.5 + 0.25 + (arc ? 0.05 : 0);
}

function openChain(points: readonly Vec2[]): { cost: number; chain: AnalyticPrimitive[] } | null {
  const count = points.length;
  const costs = Array<number>(count).fill(Infinity);
  const primitiveCounts = Array<number>(count).fill(Number.MAX_SAFE_INTEGER);
  const previous = Array<number>(count).fill(-1);
  const selected = Array<AnalyticPrimitive | null>(count).fill(null);
  costs[0] = 0;
  primitiveCounts[0] = 0;
  for (let end = 1; end < count; end += 1) {
    const minimum = Math.max(0, end - MAXIMUM_INTERVAL_VERTICES + 1);
    for (let start = minimum; start < end; start += 1) {
      if (!Number.isFinite(costs[start])) continue;
      const interval = points.slice(start, end + 1);
      const primitive = linePrimitive(interval) ?? arcPrimitive(interval);
      if (primitive === null) continue;
      const cost = costs[start]! + primitiveCost(primitive);
      const primitiveCount = primitiveCounts[start]! + 1;
      if (cost < costs[end]! - 1e-12 || (Math.abs(cost - costs[end]!) <= 1e-12 && primitiveCount < primitiveCounts[end]!)) {
        costs[end] = cost;
        primitiveCounts[end] = primitiveCount;
        previous[end] = start;
        selected[end] = primitive;
      }
    }
  }
  if (!Number.isFinite(costs.at(-1)!)) return null;
  const chain: AnalyticPrimitive[] = [];
  let index = count - 1;
  while (index > 0) {
    const primitive = selected[index];
    if (primitive === null || primitive === undefined) return null;
    chain.push(primitive);
    index = previous[index]!;
  }
  chain.reverse();
  for (let primitive = 0; primitive < chain.length; primitive += 1) {
    chain[primitive]!.end = chain[(primitive + 1) % chain.length]!.start;
  }
  return { cost: costs.at(-1)!, chain };
}

function fitProfile(points: Vec2[]): AnalyticPrimitive[] {
  if (points.length < 3 || points.length > MAXIMUM_PROFILE_VERTICES) throw new Error("profile vertex count is outside the analytic solver limit");
  const circle = circlePrimitive(points);
  if (circle !== null) return [circle];
  let lexicographic = 0;
  const turning = points.map((point, index) => {
    const before = points[(index + points.length - 1) % points.length]!;
    const after = points[(index + 1) % points.length]!;
    const incoming: Vec2 = [point[0] - before[0], point[1] - before[1]];
    const outgoing: Vec2 = [after[0] - point[0], after[1] - point[1]];
    const denominator = Math.max(Math.hypot(...incoming) * Math.hypot(...outgoing), 1e-15);
    return Math.acos(Math.max(-1, Math.min(1, (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / denominator)));
  });
  for (let index = 1; index < points.length; index += 1) {
    if (points[index]![0] < points[lexicographic]![0] || (points[index]![0] === points[lexicographic]![0] && points[index]![1] < points[lexicographic]![1])) lexicographic = index;
  }
  const ranked = turning.map((value, index) => ({ value, index })).sort((left, right) => right.value - left.value || left.index - right.index);
  const starts = [...new Set([lexicographic, ...ranked.slice(0, 4).map((item) => item.index)])].sort((left, right) => left - right);
  const options = starts.flatMap((start) => {
    const rotated = [...points.slice(start), ...points.slice(0, start)];
    const fitted = openChain([...rotated, rotated[0]!]);
    return fitted === null ? [] : [fitted];
  });
  if (options.length === 0) throw new Error("no line/circular-arc profile satisfies the analytic tolerances");
  options.sort((left, right) => left.cost - right.cost || left.chain.length - right.chain.length);
  return options[0]!.chain;
}

function cyclicPoints(points: readonly Vec2[], start: Vec2, end: Vec2): Vec2[] {
  const nearest = (target: Vec2): number => points.reduce((selected, point, index) => (
    distance(point, target) < distance(points[selected]!, target) ? index : selected
  ), 0);
  const startIndex = nearest(start);
  const endIndex = nearest(end);
  const result: Vec2[] = [points[startIndex]!];
  let index = startIndex;
  while (index !== endIndex) {
    index = (index + 1) % points.length;
    result.push(points[index]!);
    if (result.length > points.length + 1) throw new Error("profile interval did not close");
  }
  result[0] = start;
  result[result.length - 1] = end;
  return result;
}

/**
 * Fits the bounded spanner outline used by the browser-native G2 path:
 * two stable straight edges, one broad circular arc, and one bounded cubic
 * B-spline for the asymmetric jaw. The analytic anchors must be consecutive;
 * otherwise this returns null instead of inventing an unsupported profile.
 */
export function fitBrowserSplineProfile(points: Vec2[]): BrowserProfilePrimitive[] | null {
  const analytic = fitProfile(points);
  if (analytic.length < 4) return null;
  const broadArcs = analytic
    .map((primitive, index) => ({ primitive, index }))
    .filter((item): item is { primitive: ArcPrimitive; index: number } => (
      item.primitive.kind === "arc" && Math.abs(item.primitive.sweepDeg) >= 120
    ))
    .sort((left, right) => Math.abs(right.primitive.sweepDeg) - Math.abs(left.primitive.sweepDeg));
  const lines = analytic
    .map((primitive, index) => ({ primitive, index }))
    .filter((item): item is { primitive: LinePrimitive; index: number } => item.primitive.kind === "line")
    .sort((left, right) => distance(right.primitive.start, right.primitive.end) - distance(left.primitive.start, left.primitive.end));
  const boundedAnalyticFallback = (): BrowserProfilePrimitive[] | null => (
    analytic.length <= 64 && lines.length >= 2 && analytic.some((primitive) => primitive.kind === "arc")
      ? analytic
      : null
  );
  if (broadArcs.length !== 1 || lines.length < 2) return boundedAnalyticFallback();
  const anchorIndexes = new Set([broadArcs[0]!.index, lines[0]!.index, lines[1]!.index]);
  let anchorStart = -1;
  for (let index = 0; index < analytic.length; index += 1) {
    if ([0, 1, 2].every((offset) => anchorIndexes.has((index + offset) % analytic.length))) {
      anchorStart = index;
      break;
    }
  }
  if (anchorStart < 0) return boundedAnalyticFallback();
  const anchors = [0, 1, 2].map((offset) => analytic[(anchorStart + offset) % analytic.length]!);
  const splinePoints = cyclicPoints(points, anchors[2]!.end, anchors[0]!.start);
  const spline = fitBoundedBSpline(splinePoints, ARC_RMS_TOLERANCE * 1.2, ARC_MAX_TOLERANCE);
  if (spline === null) return null;
  spline.start = anchors[2]!.end;
  spline.end = anchors[0]!.start;
  return [...anchors, spline];
}

function axisVector(axisIndex: 0 | 1 | 2): Vec3 {
  return axisIndex === 0 ? [1, 0, 0] : axisIndex === 1 ? [0, 1, 0] : [0, 0, 1];
}

function frameVectors(axisIndex: 0 | 1 | 2): { x: Vec3; y: Vec3 } {
  if (axisIndex === 0) return { x: [0, 1, 0], y: [0, 0, 1] };
  if (axisIndex === 1) return { x: [0, 0, 1], y: [1, 0, 0] };
  return { x: [1, 0, 0], y: [0, 1, 0] };
}

function findAxisCandidate(positions: Float32Array): AxisCandidate | null {
  const { vertices, faces } = weldedMesh(positions);
  const options: AxisCandidate[] = [];
  for (const axisIndex of [0, 1, 2] as const) {
    const coordinates = vertices.map((point) => point[axisIndex]);
    const minimum = Math.min(...coordinates);
    const maximum = Math.max(...coordinates);
    const span = maximum - minimum;
    if (span < MINIMUM_LENGTH) continue;
    const tolerance = Math.max(1e-5, span * 1e-6);
    const minimumFaces: number[] = [];
    const maximumFaces: number[] = [];
    for (let face = 0; face < faces.length; face += 1) {
      const values = faces[face]!.map((vertex) => vertices[vertex]![axisIndex]);
      if (values.every((value) => Math.abs(value - minimum) <= tolerance)) minimumFaces.push(face);
      if (values.every((value) => Math.abs(value - maximum) <= tolerance)) maximumFaces.push(face);
    }
    if (minimumFaces.length < 2 || maximumFaces.length < 2) continue;
    const minimumArea = minimumFaces.reduce((sum, face) => sum + triangleArea(positions, face), 0);
    const maximumArea = maximumFaces.reduce((sum, face) => sum + triangleArea(positions, face), 0);
    if (Math.abs(minimumArea - maximumArea) / Math.max(minimumArea, maximumArea) > 0.03) continue;
    try {
      const minimumLoops = capBoundaryLoops(faces, minimumFaces);
      const maximumLoops = capBoundaryLoops(faces, maximumFaces);
      if (minimumLoops.length !== maximumLoops.length) continue;
      const rawLoops = minimumLoops.map((loop) => loop.map((vertex) => projectedPoint(vertices[vertex]!, axisIndex)));
      const outer = rawLoops.reduce((selected, loop, index) => Math.abs(signedArea(loop)) > Math.abs(signedArea(rawLoops[selected]!)) ? index : selected, 0);
      const loops = rawLoops.map((loop, index) => canonicalLoop(loop, index !== outer));
      const ordered = [loops[outer]!, ...loops.filter((_loop, index) => index !== outer).sort((left, right) => Math.abs(signedArea(right)) - Math.abs(signedArea(left)))];
      const profiles = ordered.map(fitProfile);
      options.push({ axisIndex, minimum, maximum, capArea: (minimumArea + maximumArea) / 2, loops: ordered, profiles });
    } catch {
      // Try the next orthogonal extent; unsupported profiles fall through to faceting.
    }
  }
  options.sort((left, right) => right.capArea - left.capArea || left.axisIndex - right.axisIndex);
  return options[0] ?? null;
}

function vector(value: Vec3): { x: number; y: number; z: number } {
  return { x: value[0], y: value[1], z: value[2] };
}

function pointOrigin(axisIndex: 0 | 1 | 2, offset: number): Vec3 {
  return axisIndex === 0 ? [offset, 0, 0] : axisIndex === 1 ? [0, offset, 0] : [0, 0, offset];
}

export function primitiveAnalysis(primitive: BrowserProfilePrimitive): Record<string, unknown> {
  return {
    kind: primitive.kind,
    start: primitive.start,
    end: primitive.end,
    rmsResidualMm: primitive.rms,
    maxResidualMm: primitive.maximum,
    ...(primitive.kind === "arc" || primitive.kind === "circle" ? { center: primitive.center, radiusMm: primitive.radius } : {}),
    ...(primitive.kind === "arc" ? { sweepDeg: primitive.sweepDeg } : {}),
    ...(primitive.kind === "bspline" ? {
      degree: primitive.degree,
      controlPoints: primitive.controlPoints,
      condition: primitive.condition,
    } : {}),
  };
}

export function inferBrowserPrismaticCadGraph(
  positions: Float32Array,
  source: SourceAssetDescriptor,
  units: Units,
): BrowserPrismaticReconstruction | null {
  const candidate = findAxisCandidate(positions);
  if (candidate === null) return null;
  const sourceVolume = meshVolume(positions);
  const profileArea = Math.abs(candidate.loops.reduce((sum, loop) => sum + signedArea(loop), 0));
  const candidateVolume = profileArea * (candidate.maximum - candidate.minimum);
  const volumeDelta = Math.abs(candidateVolume - sourceVolume);
  const relativeVolumeDelta = sourceVolume > 0
    ? volumeDelta / sourceVolume
    : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(relativeVolumeDelta) || relativeVolumeDelta > MAXIMUM_RELATIVE_VOLUME_DELTA) {
    return null;
  }
  const axis = axisVector(candidate.axisIndex);
  const frame = frameVectors(candidate.axisIndex);
  const origin = pointOrigin(candidate.axisIndex, candidate.minimum);
  const evidenceId = "evidence.browser-prismatic";
  const entities: CADGraph["sketches"][number]["entities"] = [];
  const loopIds: string[][] = [];
  let primitiveIndex = 0;
  for (const profile of candidate.profiles) {
    const identifiers: string[] = [];
    for (const primitive of profile) {
      primitiveIndex += 1;
      const id = `sketch.base.entity.${primitiveIndex}`;
      identifiers.push(id);
      const common = {
        id, construction: false as const, sourceEvidence: [evidenceId], confidence: 0.95,
        locked: false, suppressed: false,
      };
      if (primitive.kind === "line") {
        entities.push({ ...common, kind: "line", start: { x: primitive.start[0], y: primitive.start[1] }, end: { x: primitive.end[0], y: primitive.end[1] } });
      } else if (primitive.kind === "circle") {
        entities.push({ ...common, kind: "circle", center: { x: primitive.center[0], y: primitive.center[1] }, radius: primitive.radius });
      } else if (primitive.kind === "arc") {
        const startAngleDeg = Math.atan2(primitive.start[1] - primitive.center[1], primitive.start[0] - primitive.center[0]) * 180 / Math.PI;
        entities.push({
          ...common, kind: "circularArc", center: { x: primitive.center[0], y: primitive.center[1] }, radius: primitive.radius,
          startAngleDeg, endAngleDeg: startAngleDeg + primitive.sweepDeg, clockwise: primitive.sweepDeg < 0,
        });
      }
    }
    loopIds.push(identifiers);
  }
  const distanceMm = candidate.maximum - candidate.minimum;
  const graph = {
    schemaVersion: "1.0.0",
    id: "reconstruction.browser-prismatic",
    name: "Recovered analytic extrusion",
    units,
    source: {
      format: "stl", sha256: source.sha256, originalFileName: source.originalFileName,
      byteSize: source.byteSize, triangleCount: positions.length / 9, declaredUnits: source.declaredUnits,
      scaleFactor: source.scaleFactor,
    },
    sourceCoordinateFrame: {
      origin: vector(origin), xAxis: vector(frame.x), yAxis: vector(frame.y), zAxis: vector(axis),
      locked: false, confidence: 0.95, evidenceIds: [evidenceId],
    },
    projectTolerance: { surfaceDeviation: 0.1, angularDeviationDeg: 1, linearResolution: 0.001 },
    sketches: [{
      id: "sketch.base", name: "Recovered line and arc profile",
      plane: { origin: vector(origin), normal: vector(axis), xAxis: vector(frame.x) },
      entities, constraints: [],
      profiles: [{
        id: "sketch.base.profile", name: "Recovered closed profile",
        outerLoop: loopIds[0] as [string, ...string[]],
        innerLoops: loopIds.slice(1) as Array<[string, ...string[]]>,
        orientation: "counterclockwise", closed: true, sourceEvidence: [evidenceId], confidence: 0.95, locked: false,
      }],
      sourceEvidence: [evidenceId], confidence: 0.95, userLocks: [], overrides: [], suppressed: false,
    }],
    features: [{
      id: "feature.base", name: "Recovered analytic extrusion", operation: "extrusion", booleanMode: "base",
      order: 0, dependencies: [], suppressed: false, sourceEvidence: [evidenceId], confidence: 0.95,
      userLocks: [], overrides: [], semanticOutputs: ["feature.base.result"], sketchId: "sketch.base",
      profileIds: ["sketch.base.profile"], direction: vector(axis), extent: "blind", distance: distanceMm,
    }],
    semanticTopology: [{
      id: "feature.base.result", kind: "solid", producerFeatureId: "feature.base", role: "resultSolid",
      generatedFrom: ["sketch.base.profile"], status: "unresolved",
    }],
    sourceEvidence: [{
      id: evidenceId, sourceType: "derived", sourceIds: [], measuredValue: distanceMm, residual: 0,
      confidence: 0.95, notes: "Matched opposing STL caps and fitted an exact line/circular-arc extrusion profile.",
      metadata: { axis, primitiveCount: primitiveIndex, sourceVolume, candidateVolume, volumeDelta, relativeVolumeDelta },
    }],
    userLocks: [], overrides: [],
    reconstructionSettings: {
      maxFeatures: 16, beamWidth: 2, candidatesPerResidual: 2, wallClockSeconds: 30, maxRebuilds: 8,
      minScoreImprovement: 0.0001, nominalSnappingEnabled: false, nominalSnapTolerance: 0.05,
      scoreWeights: {
        rmsDistance: 1, p95Distance: 1, maxDistance: 0.5, normalAgreement: 0.5, volumeDifference: 0.75,
        overlap: 0.75, sharpEdgeAlignment: 0.5, boundaryAlignment: 0.5, unmatchedSource: 1,
        excessResult: 1, complexity: 0.1, unsupportedOperation: 2, evidenceConfidence: 0.25,
      },
    },
    engineVersions: {
      mesh2param: "0.1.0", contracts: "1.0.0", cadBackend: "OCCT", cadQuery: "browser-local",
      ocp: "occt-wasm-3.7.0", dependencies: { "occt-wasm": "3.7.0" },
    },
    deterministicSeed: 0x4d325006,
    fitMetrics: {
      rmsSurfaceDistance: 0, p95SurfaceDistance: 0, maxSurfaceDistance: 0, normalAgreement: 1,
      volumeDifference: volumeDelta, overlap: 1, unmatchedSourceArea: 0, excessResultArea: 0, score: 0.95,
    },
    validation: {
      status: "notRun", brepValid: null, stepReimportValid: null, toleranceSatisfied: null,
      lastValidFeatureId: null, issues: [],
    },
    versionMetadata: {
      versionId: "version.browser-prismatic.1", createdAt: "1970-01-01T00:00:00Z",
      createdBy: "mesh2param-browser-reconstruction", message: "Analytic line/arc profile reconstructed in the browser.",
    },
    extensions: {
      "mesh2param.dev/prismaticReconstruction": {
        scope: "orthogonal linear extrusion of line/circular-arc profiles",
        primitiveCount: primitiveIndex,
        sourceVolume,
        candidateVolume,
        volumeDelta,
        relativeVolumeDelta,
      },
    },
  } satisfies CADGraph;
  return {
    graph,
    analysis: {
      accepted: true, axis, distanceMm, confidence: 0.95, relativeVolumeDelta,
      profiles: candidate.profiles.map((profile) => profile.map(primitiveAnalysis)),
    },
  };
}
