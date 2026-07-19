import { EigenvalueDecomposition, Matrix } from "ml-matrix";

import type { BrowserTriangleMesh } from "./mesh";

export type Vec2 = [number, number];
export type Vec3Tuple = [number, number, number];

export interface ProjectionFrame {
  origin: Vec3Tuple;
  u: Vec3Tuple;
  v: Vec3Tuple;
  w: Vec3Tuple;
}

export interface BrowserSectionLoop {
  points: Vec2[];
  signedArea: number;
  bounds: [number, number, number, number];
  isHole: boolean;
}

export interface BrowserSectionSlice {
  index: number;
  offset: number;
  normalizedHeight: number;
  loops: BrowserSectionLoop[];
  sourceTriangleIds: number[];
}

export interface BrowserRadiusFit {
  accepted: boolean;
  radius: number | null;
  rmsResidual: number | null;
  maximumResidual: number | null;
  maximumInset: number;
}

export interface BrowserChamferFit {
  accepted: boolean;
  width: number | null;
  rmsResidual: number | null;
  maximumResidual: number | null;
  maximumInset: number;
}

export interface BrowserSectionStack {
  axis: Vec3Tuple;
  frame: ProjectionFrame;
  capOffsets: [number, number];
  slices: BrowserSectionSlice[];
  referenceSliceIndex: number;
  radiusFit: BrowserRadiusFit;
  chamferFit: BrowserChamferFit;
  blindFeatureDetected: boolean;
  taperedExtrusionDetected: boolean;
  maximumSupportChange: number;
}

function dot(left: Vec3Tuple, right: Vec3Tuple): number {
  return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

function normalize(value: Vec3Tuple): Vec3Tuple {
  const magnitude = Math.hypot(...value);
  if (!Number.isFinite(magnitude) || magnitude <= 1e-15) throw new Error("Section axis is not finite");
  return [value[0] / magnitude, value[1] / magnitude, value[2] / magnitude];
}

function canonicalAxis(value: Vec3Tuple): Vec3Tuple {
  const axis = normalize(value);
  const dominant = Math.abs(axis[0]) >= Math.abs(axis[1]) && Math.abs(axis[0]) >= Math.abs(axis[2])
    ? 0
    : Math.abs(axis[1]) >= Math.abs(axis[2]) ? 1 : 2;
  return axis[dominant]! < 0 ? [-axis[0], -axis[1], -axis[2]] : axis;
}

export function estimateSectionAxis(mesh: BrowserTriangleMesh): Vec3Tuple {
  const moment = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let face = 0; face < mesh.triangleCount; face += 1) {
    const normal: Vec3Tuple = [
      mesh.faceNormals[face * 3]!, mesh.faceNormals[face * 3 + 1]!, mesh.faceNormals[face * 3 + 2]!,
    ];
    const area = mesh.faceAreas[face]!;
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 3; column += 1) moment[row]![column]! += area * normal[row]! * normal[column]!;
    }
  }
  const decomposition = new EigenvalueDecomposition(new Matrix(moment), { assumeSymmetric: true });
  let index = 0;
  for (let candidate = 1; candidate < 3; candidate += 1) {
    if (decomposition.realEigenvalues[candidate]! > decomposition.realEigenvalues[index]!) index = candidate;
  }
  const principal = canonicalAxis([
    decomposition.eigenvectorMatrix.get(0, index),
    decomposition.eigenvectorMatrix.get(1, index),
    decomposition.eigenvectorMatrix.get(2, index),
  ]);
  // The normal-moment eigenvector is a stable coarse axis, but small embossed
  // details can tilt it enough that a large planar cap is split into many
  // artificial offset levels. Refine it from the area-weighted cap-normal
  // cluster. Sign-align opposite caps before averaging so arbitrary model
  // orientation is preserved and paired caps reinforce one another.
  const capCosine = Math.cos(5 * Math.PI / 180);
  let capAnchor: Vec3Tuple | null = null;
  let capAnchorArea = 0;
  for (let face = 0; face < mesh.triangleCount; face += 1) {
    const normal: Vec3Tuple = [
      mesh.faceNormals[face * 3]!, mesh.faceNormals[face * 3 + 1]!, mesh.faceNormals[face * 3 + 2]!,
    ];
    if (Math.abs(dot(normal, principal)) < capCosine || mesh.faceAreas[face]! <= capAnchorArea) continue;
    const sign = dot(normal, principal) < 0 ? -1 : 1;
    capAnchor = [sign * normal[0], sign * normal[1], sign * normal[2]];
    capAnchorArea = mesh.faceAreas[face]!;
  }
  if (capAnchor === null) return principal;
  const refined: Vec3Tuple = [0, 0, 0];
  let refinedArea = 0;
  const clusterCosine = Math.cos(0.1 * Math.PI / 180);
  for (let face = 0; face < mesh.triangleCount; face += 1) {
    const normal: Vec3Tuple = [
      mesh.faceNormals[face * 3]!, mesh.faceNormals[face * 3 + 1]!, mesh.faceNormals[face * 3 + 2]!,
    ];
    const alignment = dot(normal, capAnchor);
    if (Math.abs(alignment) < clusterCosine) continue;
    const sign = alignment < 0 ? -1 : 1;
    const area = mesh.faceAreas[face]!;
    refined[0] += sign * area * normal[0];
    refined[1] += sign * area * normal[1];
    refined[2] += sign * area * normal[2];
    refinedArea += area;
  }
  return refinedArea > 1e-15 ? canonicalAxis(refined) : principal;
}

function projectionFrame(axisValue: Vec3Tuple, origin: Vec3Tuple): ProjectionFrame {
  const w = normalize(axisValue);
  const basis: Vec3Tuple[] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const selected = basis.reduce((best, value) => Math.abs(dot(value, w)) < Math.abs(dot(best, w)) ? value : best);
  const projected: Vec3Tuple = [
    selected[0] - w[0] * dot(selected, w),
    selected[1] - w[1] * dot(selected, w),
    selected[2] - w[2] * dot(selected, w),
  ];
  let u = normalize(projected);
  const dominant = Math.abs(u[0]) >= Math.abs(u[1]) && Math.abs(u[0]) >= Math.abs(u[2]) ? 0 : Math.abs(u[1]) >= Math.abs(u[2]) ? 1 : 2;
  if (u[dominant]! < 0) u = [-u[0], -u[1], -u[2]];
  const v = normalize([
    w[1] * u[2] - w[2] * u[1],
    w[2] * u[0] - w[0] * u[2],
    w[0] * u[1] - w[1] * u[0],
  ]);
  return { origin, u, v, w };
}

function project(frame: ProjectionFrame, point: Vec3Tuple): Vec2 {
  const relative: Vec3Tuple = [point[0] - frame.origin[0], point[1] - frame.origin[1], point[2] - frame.origin[2]];
  return [dot(relative, frame.u), dot(relative, frame.v)];
}

function primaryCapOffsets(mesh: BrowserTriangleMesh, axis: Vec3Tuple, tolerance: number): [number, number] {
  const cosine = Math.cos(2 * Math.PI / 180);
  const samples: Array<{ offset: number; area: number }> = [];
  for (let face = 0; face < mesh.triangleCount; face += 1) {
    const normal: Vec3Tuple = [mesh.faceNormals[face * 3]!, mesh.faceNormals[face * 3 + 1]!, mesh.faceNormals[face * 3 + 2]!];
    if (Math.abs(dot(normal, axis)) < cosine) continue;
    const center: Vec3Tuple = [mesh.faceCenters[face * 3]!, mesh.faceCenters[face * 3 + 1]!, mesh.faceCenters[face * 3 + 2]!];
    samples.push({ offset: dot(center, axis), area: mesh.faceAreas[face]! });
  }
  if (samples.length < 2) throw new Error("Fewer than two cap-aligned faces exist");
  samples.sort((left, right) => left.offset - right.offset);
  const mergeTolerance = Math.max(tolerance * 0.6, 1e-6);
  const levels: Array<{ weighted: number; area: number }> = [];
  for (const sample of samples) {
    const current = levels.at(-1);
    if (current === undefined || Math.abs(sample.offset - current.weighted / current.area) > mergeTolerance) {
      levels.push({ weighted: sample.offset * sample.area, area: sample.area });
    } else {
      current.weighted += sample.offset * sample.area;
      current.area += sample.area;
    }
  }
  let best: { low: number; high: number; score: number; extent: number } | null = null;
  for (let left = 0; left < levels.length; left += 1) {
    for (let right = left + 1; right < levels.length; right += 1) {
      const low = levels[left]!.weighted / levels[left]!.area;
      const high = levels[right]!.weighted / levels[right]!.area;
      const extent = high - low;
      if (extent < Math.max(tolerance * 2, 1e-4)) continue;
      const candidate = { low, high, score: Math.min(levels[left]!.area, levels[right]!.area), extent };
      if (best === null || candidate.score > best.score + 1e-12 || (Math.abs(candidate.score - best.score) <= 1e-12 && candidate.extent > best.extent)) best = candidate;
    }
  }
  if (best === null) throw new Error("No separated primary cap pair was measured");
  return [best.low, best.high];
}

interface Segment { start: Vec3Tuple; end: Vec3Tuple; triangle: number }

function distance3(left: Vec3Tuple, right: Vec3Tuple): number {
  return Math.hypot(left[0] - right[0], left[1] - right[1], left[2] - right[2]);
}

function sectionSegments(mesh: BrowserTriangleMesh, axis: Vec3Tuple, offset: number, epsilon: number): Segment[] {
  const segments: Segment[] = [];
  for (let face = 0; face < mesh.triangleCount; face += 1) {
    const points: Vec3Tuple[] = [0, 1, 2].map((corner) => {
      const vertex = mesh.faces[face * 3 + corner]! * 3;
      return [mesh.vertices[vertex]!, mesh.vertices[vertex + 1]!, mesh.vertices[vertex + 2]!] as Vec3Tuple;
    });
    const distances = points.map((point) => dot(point, axis) - offset);
    if (Math.min(...distances) > epsilon || Math.max(...distances) < -epsilon) continue;
    const intersections: Vec3Tuple[] = [];
    for (const [first, second] of [[0, 1], [1, 2], [2, 0]] as const) {
      const a = points[first]!; const b = points[second]!;
      const da = distances[first]!; const db = distances[second]!;
      if (Math.abs(da) <= epsilon) intersections.push(a);
      if ((da < -epsilon && db > epsilon) || (da > epsilon && db < -epsilon)) {
        const fraction = da / (da - db);
        intersections.push([
          a[0] + (b[0] - a[0]) * fraction,
          a[1] + (b[1] - a[1]) * fraction,
          a[2] + (b[2] - a[2]) * fraction,
        ]);
      }
    }
    const unique = intersections.filter((point, index) => intersections.slice(0, index).every((other) => distance3(point, other) > epsilon));
    if (unique.length < 2) continue;
    let pair: [Vec3Tuple, Vec3Tuple] = [unique[0]!, unique[1]!];
    for (let left = 0; left < unique.length; left += 1) for (let right = left + 1; right < unique.length; right += 1) {
      if (distance3(unique[left]!, unique[right]!) > distance3(pair[0], pair[1])) pair = [unique[left]!, unique[right]!];
    }
    if (distance3(pair[0], pair[1]) > epsilon) segments.push({ start: pair[0], end: pair[1], triangle: face });
  }
  return segments;
}

function pointKey(point: Vec3Tuple, tolerance: number): string {
  return `${Math.round(point[0] / tolerance)}:${Math.round(point[1] / tolerance)}:${Math.round(point[2] / tolerance)}`;
}

function assembleLoops(segmentValues: Segment[], tolerance: number): Array<{ points: Vec3Tuple[]; triangles: number[] }> {
  // Booleaned or highly tessellated solids can contain coincident section
  // segments from paired triangles. They are identical geometric evidence,
  // but retaining both creates artificial degree-four vertices in the loop
  // graph. Collapse them by their quantized undirected endpoints.
  const uniqueSegments = new Map<string, Segment>();
  for (const segment of segmentValues) {
    const start = pointKey(segment.start, tolerance);
    const end = pointKey(segment.end, tolerance);
    const key = start < end ? `${start}|${end}` : `${end}|${start}`;
    if (!uniqueSegments.has(key)) uniqueSegments.set(key, segment);
  }
  const segments = [...uniqueSegments.values()];
  const adjacency = new Map<string, number[]>();
  for (let index = 0; index < segments.length; index += 1) {
    for (const point of [segments[index]!.start, segments[index]!.end]) {
      const key = pointKey(point, tolerance);
      const items = adjacency.get(key) ?? [];
      items.push(index);
      adjacency.set(key, items);
    }
  }
  const used = new Set<number>();
  const loops: Array<{ points: Vec3Tuple[]; triangles: number[] }> = [];
  for (let seed = 0; seed < segments.length; seed += 1) {
    if (used.has(seed)) continue;
    const first = segments[seed]!;
    const startKey = pointKey(first.start, tolerance);
    const points: Vec3Tuple[] = [first.start, first.end];
    const triangles = [first.triangle];
    used.add(seed);
    let currentKey = pointKey(first.end, tolerance);
    let guard = 0;
    while (currentKey !== startKey && guard <= segments.length) {
      guard += 1;
      const candidates = (adjacency.get(currentKey) ?? []).filter((index) => !used.has(index)).sort((a, b) => a - b);
      if (candidates.length === 0) break;
      const index = candidates[0]!;
      const segment = segments[index]!;
      const startMatches = pointKey(segment.start, tolerance) === currentKey;
      const next = startMatches ? segment.end : segment.start;
      points.push(next);
      triangles.push(segment.triangle);
      used.add(index);
      currentKey = pointKey(next, tolerance);
    }
    if (currentKey !== startKey || points.length < 4) {
      const degrees = [...adjacency.values()].map((items) => items.length);
      throw new Error(
        `Section path did not form a bounded closed loop (segments=${segments.length}, used=${used.size}, points=${points.length}, currentDegree=${adjacency.get(currentKey)?.length ?? 0}, minDegree=${Math.min(...degrees)}, maxDegree=${Math.max(...degrees)})`,
      );
    }
    points.pop();
    loops.push({ points, triangles });
  }
  return loops;
}

function signedArea(points: readonly Vec2[]): number {
  let result = 0;
  for (let index = 0; index < points.length; index += 1) {
    const next = (index + 1) % points.length;
    result += points[index]![0] * points[next]![1] - points[index]![1] * points[next]![0];
  }
  return result / 2;
}

function removeCollinear(points: Vec2[], tolerance: number): Vec2[] {
  let result = [...points];
  let changed = true;
  while (changed && result.length > 3) {
    changed = false;
    result = result.filter((point, index) => {
      const previous = result[(index + result.length - 1) % result.length]!;
      const following = result[(index + 1) % result.length]!;
      const dx = following[0] - previous[0]; const dy = following[1] - previous[1];
      const length = Math.hypot(dx, dy);
      if (length <= 1e-15) { changed = true; return false; }
      const perpendicular = Math.abs(dx * (previous[1] - point[1]) - dy * (previous[0] - point[0])) / length;
      const between = (point[0] - previous[0]) * (point[0] - following[0]) + (point[1] - previous[1]) * (point[1] - following[1]) <= tolerance * tolerance;
      if (perpendicular <= tolerance && between) { changed = true; return false; }
      return true;
    });
  }
  return result;
}

function canonicalLoop(pointsValue: Vec2[], clockwise: boolean): BrowserSectionLoop {
  let points = removeCollinear(pointsValue, 1e-5);
  let area = signedArea(points);
  if ((area < 0) !== clockwise) { points = [...points].reverse(); area = -area; }
  let start = 0;
  for (let index = 1; index < points.length; index += 1) {
    if (points[index]![0] < points[start]![0] - 1e-12 || (Math.abs(points[index]![0] - points[start]![0]) <= 1e-12 && points[index]![1] < points[start]![1])) start = index;
  }
  points = [...points.slice(start), ...points.slice(0, start)];
  return {
    points,
    signedArea: area,
    bounds: [
      Math.min(...points.map((point) => point[0])), Math.min(...points.map((point) => point[1])),
      Math.max(...points.map((point) => point[0])), Math.max(...points.map((point) => point[1])),
    ],
    isHole: clockwise,
  };
}

export function extractSectionSliceAtOffset(
  mesh: BrowserTriangleMesh,
  axis: Vec3Tuple,
  frame: ProjectionFrame,
  offset: number,
  tolerance: number,
): BrowserSectionSlice {
  const sectionEpsilon = Math.max(tolerance * 1e-5, 1e-9);
  const joinTolerance = Math.max(tolerance * 1e-4, 1e-8);
  const segments = sectionSegments(mesh, axis, offset, sectionEpsilon);
  const assembled = assembleLoops(segments, joinTolerance);
  const projected = assembled.map((loop) => ({
    points: loop.points.map((point) => project(frame, point)),
    triangles: loop.triangles,
  })).sort((left, right) => Math.abs(signedArea(right.points)) - Math.abs(signedArea(left.points)));
  if (projected.length === 0 || projected.length > 64) throw new Error("Section has an unsupported loop count");
  return {
    index: 0,
    offset,
    normalizedHeight: 0,
    loops: projected.map((loop, loopIndex) => canonicalLoop(loop.points, loopIndex > 0)),
    sourceTriangleIds: [...new Set(assembled.flatMap((loop) => loop.triangles))].sort((left, right) => left - right),
  };
}

function circleInset(distance: number, radius: number): number {
  if (distance >= radius) return 0;
  return radius - Math.sqrt(Math.max(0, radius * radius - (radius - Math.min(distance, radius)) ** 2));
}

function goldenSectionMinimum(objective: (value: number) => number, lowerValue: number, upperValue: number): number {
  const ratio = (Math.sqrt(5) - 1) / 2;
  let lower = lowerValue; let upper = upperValue;
  let left = upper - ratio * (upper - lower); let right = lower + ratio * (upper - lower);
  let leftValue = objective(left); let rightValue = objective(right);
  for (let iteration = 0; iteration < 128 && upper - lower > 1e-10; iteration += 1) {
    if (leftValue <= rightValue) {
      upper = right; right = left; rightValue = leftValue; left = upper - ratio * (upper - lower); leftValue = objective(left);
    } else {
      lower = left; left = right; leftValue = rightValue; right = lower + ratio * (upper - lower); rightValue = objective(right);
    }
  }
  return (lower + upper) / 2;
}

function measureSectionInsets(
  slices: BrowserSectionSlice[],
  reference: BrowserSectionSlice,
  caps: [number, number],
): { distances: number[]; insets: number[] } {
  const distances: number[] = [];
  const insets: number[] = [];
  for (const slice of slices) {
    const current = slice.loops[0]!.bounds;
    const expected = reference.loops[0]!.bounds;
    const supportInsets = [current[0] - expected[0], current[1] - expected[1], expected[2] - current[2], expected[3] - current[3]].sort((a, b) => a - b);
    insets.push(Math.max(0, (supportInsets[1]! + supportInsets[2]!) / 2));
    distances.push(Math.min(slice.offset - caps[0], caps[1] - slice.offset));
  }
  return { distances, insets };
}

function fitRadius(slices: BrowserSectionSlice[], reference: BrowserSectionSlice, caps: [number, number], tolerance: number): BrowserRadiusFit {
  const { distances, insets } = measureSectionInsets(slices, reference, caps);
  const maximumInset = Math.max(...insets);
  const minimumRadius = Math.max(tolerance * 2, 1e-4);
  const maximumRadius = (caps[1] - caps[0]) * 0.45;
  if (maximumRadius <= minimumRadius) return { accepted: false, radius: null, rmsResidual: null, maximumResidual: null, maximumInset };
  const radius = goldenSectionMinimum((candidate) => {
    const squared = distances.map((distance, index) => (circleInset(distance, candidate) - insets[index]!) ** 2);
    return squared.reduce((sum, value) => sum + value, 0) / squared.length;
  }, minimumRadius, maximumRadius);
  const residuals = distances.map((distance, index) => Math.abs(circleInset(distance, radius) - insets[index]!));
  const rmsResidual = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / residuals.length);
  const maximumResidual = Math.max(...residuals);
  return {
    accepted: maximumInset >= Math.max(tolerance * 1.6, 1e-4) && rmsResidual <= tolerance * 0.6 && maximumResidual <= tolerance * 1.6,
    radius,
    rmsResidual,
    maximumResidual,
    maximumInset,
  };
}

function fitChamfer(slices: BrowserSectionSlice[], reference: BrowserSectionSlice, caps: [number, number], tolerance: number): BrowserChamferFit {
  const { distances, insets } = measureSectionInsets(slices, reference, caps);
  const maximumInset = Math.max(...insets);
  const minimumWidth = Math.max(tolerance * 2, 1e-4);
  const maximumWidth = (caps[1] - caps[0]) * 0.45;
  if (maximumWidth <= minimumWidth) return { accepted: false, width: null, rmsResidual: null, maximumResidual: null, maximumInset };
  const width = goldenSectionMinimum((candidate) => {
    const squared = distances.map((distance, index) => (Math.max(0, candidate - distance) - insets[index]!) ** 2);
    return squared.reduce((sum, value) => sum + value, 0) / squared.length;
  }, minimumWidth, maximumWidth);
  const residuals = distances.map((distance, index) => Math.abs(Math.max(0, width - distance) - insets[index]!));
  const rmsResidual = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / residuals.length);
  const maximumResidual = Math.max(...residuals);
  return {
    accepted: maximumInset >= Math.max(tolerance * 1.6, 1e-4) && rmsResidual <= tolerance * 0.6 && maximumResidual <= tolerance * 1.6,
    width,
    rmsResidual,
    maximumResidual,
    maximumInset,
  };
}

export function extractSectionStack(mesh: BrowserTriangleMesh, tolerance: number, sectionCount = 32): BrowserSectionStack {
  if (!Number.isFinite(tolerance) || tolerance <= 0) throw new Error("Section tolerance must be finite and positive");
  const axis = estimateSectionAxis(mesh);
  const capOffsets = primaryCapOffsets(mesh, axis, tolerance);
  const frame = projectionFrame(axis, [axis[0] * capOffsets[0], axis[1] * capOffsets[0], axis[2] * capOffsets[0]]);
  const extent = capOffsets[1] - capOffsets[0];
  const slices: BrowserSectionSlice[] = [];
  const sectionEpsilon = Math.max(tolerance * 1e-5, 1e-9);
  for (let index = 0; index < sectionCount; index += 1) {
    const targetNormalizedHeight = (index + 1) / (sectionCount + 1);
    const targetOffset = capOffsets[0] + targetNormalizedHeight * extent;
    // A nominal section can land exactly on a tessellation ring or high-valence
    // vertex, producing a degree-four intersection graph even for a watertight
    // solid. Retry at deterministic sub-tolerance offsets; this changes neither
    // the inferred units nor the feature scale, but avoids a combinatorial
    // artifact of the source triangulation.
    const jitter = Math.max(tolerance * 1e-3, 1e-7);
    const candidateOffsets = [targetOffset, targetOffset + jitter, targetOffset - jitter, targetOffset + 2 * jitter, targetOffset - 2 * jitter]
      .filter((candidate) => candidate > capOffsets[0] + sectionEpsilon && candidate < capOffsets[1] - sectionEpsilon);
    let selected: BrowserSectionSlice | null = null;
    let selectedOffset = targetOffset;
    let lastError: unknown = null;
    for (const candidateOffset of candidateOffsets) {
      try {
        selected = extractSectionSliceAtOffset(mesh, axis, frame, candidateOffset, tolerance);
        selectedOffset = candidateOffset;
        break;
      } catch (cause) {
        lastError = cause;
      }
    }
    if (selected === null) {
      throw new Error(`Section ${index} at offset ${targetOffset}: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
    }
    slices.push({
      index,
      offset: selectedOffset,
      normalizedHeight: (selectedOffset - capOffsets[0]) / extent,
      loops: selected.loops,
      sourceTriangleIds: selected.sourceTriangleIds,
    });
  }
  const countFrequency = new Map<number, number>();
  for (const slice of slices) countFrequency.set(slice.loops.length, (countFrequency.get(slice.loops.length) ?? 0) + 1);
  const dominantLoopCount = [...countFrequency.entries()].sort((left, right) => right[1] - left[1] || left[0] - right[0])[0]![0];
  const stableSlices = slices.filter((slice) => slice.loops.length === dominantLoopCount);
  const middle = stableSlices.filter((slice) => slice.normalizedHeight >= 0.4 && slice.normalizedHeight <= 0.6);
  const reference = middle.reduce((best, slice) => Math.abs(slice.loops[0]!.signedArea) > Math.abs(best.loops[0]!.signedArea) ? slice : best);
  const radiusFit = fitRadius(stableSlices, reference, capOffsets, tolerance);
  const chamferFit = fitChamfer(stableSlices, reference, capOffsets, tolerance);
  const supportSlices = stableSlices.filter((slice) => slice.normalizedHeight >= 0.15 && slice.normalizedHeight <= 0.85);
  const supports = supportSlices.map((slice) => slice.loops[0]!.bounds);
  const supportChanges = supports.slice(1).map((bounds) => Math.max(
    ...bounds.map((value, axisIndex) => Math.abs(value - reference.loops[0]!.bounds[axisIndex]!)),
  )).sort((left, right) => left - right);
  // A section exactly through a triangulation vertex can contain a local
  // combinatorial outlier. Taper is a persistent stack property, so use the
  // deterministic 90th percentile rather than a single worst slice.
  const totalSupportChange = supportChanges[Math.floor(0.9 * (supportChanges.length - 1))] ?? 0;
  return {
    axis,
    frame,
    capOffsets,
    slices,
    referenceSliceIndex: reference.index,
    radiusFit,
    chamferFit,
    blindFeatureDetected: stableSlices.length / slices.length < 0.8,
    taperedExtrusionDetected: !radiusFit.accepted && !chamferFit.accepted && totalSupportChange > tolerance * 2,
    maximumSupportChange: totalSupportChange,
  };
}
