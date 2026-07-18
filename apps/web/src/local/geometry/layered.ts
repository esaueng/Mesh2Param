import type { OcctKernel, ShapeHandle, Vec3 } from "occt-wasm";

type Vec2 = [number, number];
type AxisIndex = 0 | 1 | 2;

interface SliceLoop {
  points: Vec2[];
  area: number;
  centroid: Vec2;
  depth: number;
}

interface SliceSection {
  coordinate: number;
  outer: SliceLoop;
  holes: SliceLoop[];
}

interface HoleObservation {
  sectionIndex: number;
  coordinate: number;
  loop: SliceLoop;
}

interface HoleTrack {
  observations: HoleObservation[];
}

interface OuterProfile {
  coordinate: number;
  outer: SliceLoop;
}

export interface LayeredCurvedEvidence {
  axisIndex: AxisIndex;
  sectionCount: number;
  outerProfileCount: number;
  holeTrackCount: number;
  sourceTriangleCount: number;
  reconstructionMode: "smooth-loft" | "representative-extrusion";
}

export interface LayeredCurvedShape {
  shape: ShapeHandle;
  evidence: LayeredCurvedEvidence;
}

// Keep the section network bounded. Dense, nearly coincident loft sections
// make downstream OCCT surface/surface intersections disproportionately slow
// without adding useful accuracy at the UI's fitting tolerance.
const SECTION_COUNT = 33;
const MAX_CURVE_POINTS = 512;
const MINIMUM_LOOP_AREA_RATIO = 1e-7;

function signedArea(points: readonly Vec2[]): number {
  let result = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]!;
    const following = points[(index + 1) % points.length]!;
    result += current[0] * following[1] - current[1] * following[0];
  }
  return result / 2;
}

function polygonCentroid(points: readonly Vec2[]): Vec2 {
  const area = signedArea(points);
  if (Math.abs(area) <= 1e-18) {
    return [
      points.reduce((sum, point) => sum + point[0], 0) / points.length,
      points.reduce((sum, point) => sum + point[1], 0) / points.length,
    ];
  }
  let x = 0;
  let y = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]!;
    const following = points[(index + 1) % points.length]!;
    const cross = current[0] * following[1] - following[0] * current[1];
    x += (current[0] + following[0]) * cross;
    y += (current[1] + following[1]) * cross;
  }
  return [x / (6 * area), y / (6 * area)];
}

function pointInPolygon(point: Vec2, polygon: readonly Vec2[]): boolean {
  let inside = false;
  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current, current += 1) {
    const left = polygon[current]!;
    const right = polygon[previous]!;
    if (
      (left[1] > point[1]) !== (right[1] > point[1])
      && point[0] < (right[0] - left[0]) * (point[1] - left[1]) / (right[1] - left[1]) + left[0]
    ) inside = !inside;
  }
  return inside;
}

function projectedAxes(axisIndex: AxisIndex): readonly [AxisIndex, AxisIndex] {
  if (axisIndex === 0) return [1, 2];
  if (axisIndex === 1) return [2, 0];
  return [0, 1];
}

function point3(point: Vec2, coordinate: number, axisIndex: AxisIndex): Vec3 {
  if (axisIndex === 0) return { x: coordinate, y: point[0], z: point[1] };
  if (axisIndex === 1) return { x: point[1], y: coordinate, z: point[0] };
  return { x: point[0], y: point[1], z: coordinate };
}

function distanceToSegment(point: Vec2, left: Vec2, right: Vec2): number {
  const dx = right[0] - left[0];
  const dy = right[1] - left[1];
  const denominator = dx * dx + dy * dy;
  if (denominator <= 1e-24) return Math.hypot(point[0] - left[0], point[1] - left[1]);
  const parameter = Math.max(0, Math.min(1, ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / denominator));
  return Math.hypot(point[0] - (left[0] + parameter * dx), point[1] - (left[1] + parameter * dy));
}

/** Closed-loop simplifier that never moves retained source evidence. */
function simplifyClosed(points: readonly Vec2[], tolerance: number): Vec2[] {
  const result = points.map((point) => [...point] as Vec2);
  if (result.length <= 4) return result;
  let changed = true;
  while (changed && result.length > 4) {
    changed = false;
    for (let index = 0; index < result.length && result.length > 4; index += 1) {
      const previous = result[(index + result.length - 1) % result.length]!;
      const current = result[index]!;
      const following = result[(index + 1) % result.length]!;
      if (distanceToSegment(current, previous, following) <= tolerance) {
        result.splice(index, 1);
        changed = true;
        index -= 1;
      }
    }
  }
  return result;
}

function resampleClosed(points: readonly Vec2[], count: number): Vec2[] {
  const lengths = points.map((point, index) => {
    const following = points[(index + 1) % points.length]!;
    return Math.hypot(following[0] - point[0], following[1] - point[1]);
  });
  const total = lengths.reduce((sum, length) => sum + length, 0);
  if (total <= 1e-15) return [...points];
  const result: Vec2[] = [];
  let edge = 0;
  let accumulated = 0;
  for (let sample = 0; sample < count; sample += 1) {
    const target = sample * total / count;
    while (edge + 1 < lengths.length && accumulated + lengths[edge]! < target) {
      accumulated += lengths[edge]!;
      edge += 1;
    }
    const left = points[edge]!;
    const right = points[(edge + 1) % points.length]!;
    const fraction = (target - accumulated) / Math.max(lengths[edge]!, 1e-15);
    result.push([
      left[0] + (right[0] - left[0]) * fraction,
      left[1] + (right[1] - left[1]) * fraction,
    ]);
  }
  return result;
}

function canonicalize(points: Vec2[]): Vec2[] {
  let start = 0;
  for (let index = 1; index < points.length; index += 1) {
    const candidate = points[index]!;
    const selected = points[start]!;
    const xDelta = candidate[0] - selected[0];
    if (xDelta < -1e-12 || (Math.abs(xDelta) <= 1e-12 && candidate[1] < selected[1])) start = index;
  }
  return [...points.slice(start), ...points.slice(0, start)];
}

function endpointKey(point: Vec2, tolerance: number): string {
  return `${Math.round(point[0] / tolerance)}:${Math.round(point[1] / tolerance)}`;
}

function sliceLoops(
  positions: Float32Array,
  axisIndex: AxisIndex,
  coordinate: number,
  span: number,
  projectedDiagonal: number,
): SliceLoop[] {
  const [leftAxis, rightAxis] = projectedAxes(axisIndex);
  const planeEpsilon = Math.max(span * 1e-9, 1e-8);
  const weldTolerance = Math.max(projectedDiagonal * 1e-7, 1e-7);
  const vertices: Vec2[] = [];
  const vertexIds = new Map<string, number>();
  const edges = new Set<string>();
  const adjacency = new Map<number, number[]>();

  const vertexId = (point: Vec2): number => {
    const key = endpointKey(point, weldTolerance);
    const existing = vertexIds.get(key);
    if (existing !== undefined) return existing;
    const id = vertices.length;
    vertices.push(point);
    vertexIds.set(key, id);
    return id;
  };

  for (let triangle = 0; triangle < positions.length / 9; triangle += 1) {
    const points = Array.from({ length: 3 }, (_value, corner) => {
      const base = triangle * 9 + corner * 3;
      return [positions[base]!, positions[base + 1]!, positions[base + 2]!] as [number, number, number];
    });
    const intersections: Vec2[] = [];
    for (const [aIndex, bIndex] of [[0, 1], [1, 2], [2, 0]] as const) {
      const a = points[aIndex]!;
      const b = points[bIndex]!;
      const da = a[axisIndex] - coordinate;
      const db = b[axisIndex] - coordinate;
      if (Math.abs(da) <= planeEpsilon && Math.abs(db) <= planeEpsilon) continue;
      if ((da < -planeEpsilon && db < -planeEpsilon) || (da > planeEpsilon && db > planeEpsilon)) continue;
      const denominator = b[axisIndex] - a[axisIndex];
      if (Math.abs(denominator) <= planeEpsilon) continue;
      const parameter = (coordinate - a[axisIndex]) / denominator;
      if (parameter < -1e-9 || parameter > 1 + 1e-9) continue;
      const point: Vec2 = [
        a[leftAxis] + (b[leftAxis] - a[leftAxis]) * parameter,
        a[rightAxis] + (b[rightAxis] - a[rightAxis]) * parameter,
      ];
      if (!intersections.some((candidate) => Math.hypot(candidate[0] - point[0], candidate[1] - point[1]) <= weldTolerance)) {
        intersections.push(point);
      }
    }
    if (intersections.length !== 2) continue;
    const left = vertexId(intersections[0]!);
    const right = vertexId(intersections[1]!);
    if (left === right) continue;
    const key = `${Math.min(left, right)}:${Math.max(left, right)}`;
    if (edges.has(key)) continue;
    edges.add(key);
    adjacency.set(left, [...(adjacency.get(left) ?? []), right]);
    adjacency.set(right, [...(adjacency.get(right) ?? []), left]);
  }

  if (edges.size === 0 || [...adjacency.values()].some((neighbors) => neighbors.length !== 2)) return [];
  const remaining = new Set(edges);
  const rawLoops: Vec2[][] = [];
  while (remaining.size > 0) {
    const first = remaining.values().next().value as string;
    const [startText] = first.split(":");
    const start = Number(startText);
    const ids = [start];
    let previous = -1;
    let current = start;
    while (true) {
      const following = (adjacency.get(current) ?? []).find((candidate) => {
        if (candidate === previous) return false;
        const key = `${Math.min(current, candidate)}:${Math.max(current, candidate)}`;
        return remaining.has(key) || candidate === start;
      });
      if (following === undefined) return [];
      remaining.delete(`${Math.min(current, following)}:${Math.max(current, following)}`);
      if (following === start) break;
      ids.push(following);
      previous = current;
      current = following;
      if (ids.length > adjacency.size) return [];
    }
    if (ids.length >= 3) rawLoops.push(ids.map((id) => vertices[id]!));
  }

  const minimumArea = projectedDiagonal * projectedDiagonal * MINIMUM_LOOP_AREA_RATIO;
  const loops = rawLoops
    .map((points) => canonicalize(points))
    .map((points) => ({ points, area: Math.abs(signedArea(points)), centroid: polygonCentroid(points), depth: 0 }))
    .filter((loop) => loop.area > minimumArea)
    .sort((left, right) => right.area - left.area);
  for (let index = 0; index < loops.length; index += 1) {
    loops[index]!.depth = loops.slice(0, index).filter((candidate) => pointInPolygon(loops[index]!.centroid, candidate.points)).length;
  }
  return loops;
}

function bounds(positions: Float32Array): { lower: [number, number, number]; upper: [number, number, number] } {
  const lower: [number, number, number] = [Infinity, Infinity, Infinity];
  const upper: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      lower[axis] = Math.min(lower[axis]!, positions[index + axis]!);
      upper[axis] = Math.max(upper[axis]!, positions[index + axis]!);
    }
  }
  return { lower, upper };
}

function sectionCandidates(positions: Float32Array, axisIndex: AxisIndex): SliceSection[] {
  const box = bounds(positions);
  const span = box.upper[axisIndex] - box.lower[axisIndex];
  const [leftAxis, rightAxis] = projectedAxes(axisIndex);
  const projectedDiagonal = Math.hypot(
    box.upper[leftAxis] - box.lower[leftAxis],
    box.upper[rightAxis] - box.lower[rightAxis],
  );
  const sections: SliceSection[] = [];
  for (let index = 0; index < SECTION_COUNT; index += 1) {
    const fraction = (index + 0.5) / SECTION_COUNT;
    const coordinate = box.lower[axisIndex] + span * fraction;
    const loops = sliceLoops(positions, axisIndex, coordinate, span, projectedDiagonal);
    const outers = loops.filter((loop) => loop.depth % 2 === 0);
    if (outers.length === 0) continue;
    const outer = outers[0]!;
    if (outers.slice(1).some((loop) => loop.area > outer.area * 0.01)) return [];
    sections.push({
      coordinate,
      outer,
      holes: loops.filter((loop) => loop.depth % 2 === 1 && pointInPolygon(loop.centroid, outer.points)),
    });
  }
  return sections;
}

function chooseAxis(positions: Float32Array): { axisIndex: AxisIndex; sections: SliceSection[] } {
  const box = bounds(positions);
  const axes = ([0, 1, 2] as AxisIndex[]).sort((left, right) => {
    const leftSpan = box.upper[left] - box.lower[left];
    const rightSpan = box.upper[right] - box.lower[right];
    return leftSpan - rightSpan || left - right;
  });
  for (const axisIndex of axes) {
    const sections = sectionCandidates(positions, axisIndex);
    if (sections.length >= Math.floor(SECTION_COUNT * 0.8)) return { axisIndex, sections };
  }
  throw new Error("The browser curved fitter requires one axis-aligned layered solid with closed cross-sections");
}

function wireForLoop(
  kernel: OcctKernel,
  loop: SliceLoop,
  coordinate: number,
  axisIndex: AxisIndex,
  tolerance: number,
  polygonal: boolean,
): ShapeHandle {
  let points = simplifyClosed(loop.points, tolerance);
  if (!polygonal && points.length > MAX_CURVE_POINTS) points = resampleClosed(points, MAX_CURVE_POINTS);
  if (polygonal || points.length < 5) {
    const edges = points.map((point, index) => kernel.makeLineEdge(
      point3(point, coordinate, axisIndex),
      point3(points[(index + 1) % points.length]!, coordinate, axisIndex),
    ));
    return kernel.makeWire(edges);
  }
  const curvePoints = points.map((point) => point3(point, coordinate, axisIndex));
  const curve = kernel.approximatePoints([...curvePoints, curvePoints[0]!], tolerance);
  if (!kernel.curveIsClosed(curve)) {
    throw new Error("A fitted section curve did not close within the requested tolerance");
  }
  return kernel.makeWire([curve]);
}

function segmentedWireForLoop(
  kernel: OcctKernel,
  loop: SliceLoop,
  coordinate: number,
  axisIndex: AxisIndex,
  tolerance: number,
): ShapeHandle {
  let points = simplifyClosed(loop.points, tolerance);
  if (points.length > MAX_CURVE_POINTS) points = resampleClosed(points, MAX_CURVE_POINTS);
  const corners: number[] = [];
  for (let index = 0; index < points.length; index += 1) {
    const previous = points[(index + points.length - 1) % points.length]!;
    const current = points[index]!;
    const following = points[(index + 1) % points.length]!;
    const incoming: Vec2 = [current[0] - previous[0], current[1] - previous[1]];
    const outgoing: Vec2 = [following[0] - current[0], following[1] - current[1]];
    const cosine = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1])
      / Math.max(Math.hypot(...incoming) * Math.hypot(...outgoing), 1e-15);
    if (Math.acos(Math.max(-1, Math.min(1, cosine))) >= Math.PI / 8) corners.push(index);
  }
  const cornerSet = new Set(corners);
  const start = corners[0] ?? 0;
  const edges: ShapeHandle[] = [];
  let run: Vec2[] = [points[start]!];
  for (let step = 1; step <= points.length; step += 1) {
    const index = (start + step) % points.length;
    run.push(points[index]!);
    const atCorner = step < points.length && cornerSet.has(index);
    if (!atCorner && step < points.length && run.length < 8) continue;
    const collinear = run.every((point) => distanceToSegment(point, run[0]!, run.at(-1)!) <= tolerance);
    if (run.length === 2 || collinear) {
      edges.push(kernel.makeLineEdge(
        point3(run[0]!, coordinate, axisIndex),
        point3(run.at(-1)!, coordinate, axisIndex),
      ));
    } else {
      edges.push(kernel.approximatePoints(
        run.map((point) => point3(point, coordinate, axisIndex)),
        tolerance,
      ));
    }
    run = [run.at(-1)!];
  }
  return kernel.makeWire(edges);
}

function isPolygonal(loop: SliceLoop, tolerance: number): boolean {
  const simplified = simplifyClosed(loop.points, tolerance);
  if (simplified.length > 24) return false;
  let sharp = 0;
  for (let index = 0; index < simplified.length; index += 1) {
    const previous = simplified[(index + simplified.length - 1) % simplified.length]!;
    const current = simplified[index]!;
    const following = simplified[(index + 1) % simplified.length]!;
    const incoming: Vec2 = [current[0] - previous[0], current[1] - previous[1]];
    const outgoing: Vec2 = [following[0] - current[0], following[1] - current[1]];
    const cosine = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1])
      / Math.max(Math.hypot(...incoming) * Math.hypot(...outgoing), 1e-15);
    if (Math.acos(Math.max(-1, Math.min(1, cosine))) > Math.PI / 12) sharp += 1;
  }
  return sharp >= 3;
}

function trackHoles(sections: readonly SliceSection[]): HoleTrack[] {
  const tracks: HoleTrack[] = [];
  let active = new Set<number>();
  for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex += 1) {
    const section = sections[sectionIndex]!;
    const available = new Set(section.holes.map((_hole, index) => index));
    const nextActive = new Set<number>();
    for (const trackIndex of active) {
      const track = tracks[trackIndex]!;
      const previous = track.observations.at(-1)!.loop;
      let selected = -1;
      let selectedScore = Infinity;
      for (const holeIndex of available) {
        const candidate = section.holes[holeIndex]!;
        const scale = Math.max(Math.sqrt(previous.area), Math.sqrt(candidate.area), 1e-9);
        const centerDistance = Math.hypot(
          candidate.centroid[0] - previous.centroid[0],
          candidate.centroid[1] - previous.centroid[1],
        ) / scale;
        const areaChange = Math.abs(Math.log(candidate.area / previous.area));
        const score = centerDistance + areaChange;
        if (score < selectedScore) {
          selected = holeIndex;
          selectedScore = score;
        }
      }
      if (selected >= 0 && selectedScore <= 1.25) {
        track.observations.push({ sectionIndex, coordinate: section.coordinate, loop: section.holes[selected]! });
        available.delete(selected);
        nextActive.add(trackIndex);
      }
    }
    for (const holeIndex of available) {
      const trackIndex = tracks.length;
      tracks.push({ observations: [{ sectionIndex, coordinate: section.coordinate, loop: section.holes[holeIndex]! }] });
      nextActive.add(trackIndex);
    }
    active = nextActive;
  }
  return tracks;
}

function trackBounds(track: HoleTrack, sections: readonly SliceSection[]): [number, number] {
  const first = track.observations[0]!;
  const last = track.observations.at(-1)!;
  const before = sections[first.sectionIndex - 1]?.coordinate;
  const after = sections[last.sectionIndex + 1]?.coordinate;
  const spacingBefore = before === undefined
    ? (sections[1]!.coordinate - sections[0]!.coordinate)
    : first.coordinate - before;
  const spacingAfter = after === undefined
    ? (sections.at(-1)!.coordinate - sections.at(-2)!.coordinate)
    : after - last.coordinate;
  return [first.coordinate - spacingBefore / 2, last.coordinate + spacingAfter / 2];
}

function trackIsConstant(track: HoleTrack, tolerance: number): boolean {
  const reference = track.observations[Math.floor(track.observations.length / 2)]!.loop;
  return track.observations.every((observation) => (
    Math.abs(observation.loop.area - reference.area) / Math.max(reference.area, 1e-12) <= 0.02
    && Math.hypot(
      observation.loop.centroid[0] - reference.centroid[0],
      observation.loop.centroid[1] - reference.centroid[1],
    ) <= tolerance * 2
  ));
}

function meshVolume(positions: Float32Array): number {
  let signed = 0;
  for (let offset = 0; offset < positions.length; offset += 9) {
    const ax = positions[offset]!;
    const ay = positions[offset + 1]!;
    const az = positions[offset + 2]!;
    const bx = positions[offset + 3]!;
    const by = positions[offset + 4]!;
    const bz = positions[offset + 5]!;
    const cx = positions[offset + 6]!;
    const cy = positions[offset + 7]!;
    const cz = positions[offset + 8]!;
    signed += ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx);
  }
  return Math.abs(signed) / 6;
}

function loftLoopTrack(
  kernel: OcctKernel,
  observations: readonly HoleObservation[],
  extent: [number, number],
  axisIndex: AxisIndex,
  tolerance: number,
): ShapeHandle {
  const polygonal = observations.every((observation) => isPolygonal(observation.loop, tolerance));
  const reference = observations[Math.floor(observations.length / 2)]!.loop;
  const constantSection = trackIsConstant({ observations: [...observations] }, tolerance);
  if (constantSection) {
    const face = kernel.makeFace(wireForLoop(
      kernel,
      reference,
      extent[0],
      axisIndex,
      tolerance,
      polygonal,
    ));
    const distance = extent[1] - extent[0];
    if (axisIndex === 0) return kernel.extrude(face, distance, 0, 0);
    if (axisIndex === 1) return kernel.extrude(face, 0, distance, 0);
    return kernel.extrude(face, 0, 0, distance);
  }
  const profiles: Array<{ coordinate: number; loop: SliceLoop }> = [];
  const first = observations[0]!;
  const last = observations.at(-1)!;
  profiles.push({ coordinate: extent[0], loop: first.loop });
  profiles.push(...observations.map((observation) => ({ coordinate: observation.coordinate, loop: observation.loop })));
  profiles.push({ coordinate: extent[1], loop: last.loop });
  const deduplicated = profiles.filter((profile, index) => index === 0 || Math.abs(profile.coordinate - profiles[index - 1]!.coordinate) > 1e-10);
  return kernel.loft(
    deduplicated.map((profile) => wireForLoop(kernel, profile.loop, profile.coordinate, axisIndex, tolerance, polygonal)),
    true,
    false,
  );
}

function outerLoopAt(
  positions: Float32Array,
  axisIndex: AxisIndex,
  coordinate: number,
  fallback: SliceLoop,
): SliceLoop {
  const box = bounds(positions);
  const span = box.upper[axisIndex] - box.lower[axisIndex];
  const [leftAxis, rightAxis] = projectedAxes(axisIndex);
  const projectedDiagonal = Math.hypot(
    box.upper[leftAxis] - box.lower[leftAxis],
    box.upper[rightAxis] - box.lower[rightAxis],
  );
  const outer = sliceLoops(positions, axisIndex, coordinate, span, projectedDiagonal)
    .filter((loop) => loop.depth % 2 === 0)
    .sort((left, right) => right.area - left.area)[0];
  return outer ?? fallback;
}

function loftOuterProfiles(
  kernel: OcctKernel,
  profiles: readonly OuterProfile[],
  axisIndex: AxisIndex,
  tolerance: number,
): ShapeHandle {
  if (profiles.length < 2) throw new Error("A curved loft segment requires at least two section profiles");
  return kernel.loft(
    profiles.map((profile) => wireForLoop(
      kernel,
      profile.outer,
      profile.coordinate,
      axisIndex,
      tolerance,
      false,
    )),
    true,
    false,
  );
}

function axisSpan(kernel: OcctKernel, shape: ShapeHandle, axisIndex: AxisIndex): number {
  const box = kernel.getBoundingBox(shape, false);
  if (axisIndex === 0) return box.xmax - box.xmin;
  if (axisIndex === 1) return box.ymax - box.ymin;
  return box.zmax - box.zmin;
}

function planarCapWithHole(
  kernel: OcctKernel,
  outerWire: ShapeHandle,
  holeWire: ShapeHandle,
  expectedArea: number,
): ShapeHandle {
  const reversedHole = kernel.reverseShape(holeWire);
  const candidates: ShapeHandle[] = [];
  for (const candidateHole of [holeWire, reversedHole]) {
    try {
      candidates.push(kernel.addHolesInFace(kernel.makeFace(outerWire), [candidateHole]));
    } catch {
      // Try the alternate orientation and the planar boolean below.
    }
    try {
      // OCCT's direct wire insertion is strict about p-curve/orientation data
      // on approximated periodic edges. A planar face cut produces the same
      // B-Rep topology when that constructor rejects it.
      candidates.push(kernel.cut(kernel.makeFace(outerWire), kernel.makeFace(candidateHole)));
    } catch {
      // The direct insertion candidate may still be usable.
    }
  }
  if (candidates.length === 0) throw new Error("The curved fitter could not build a planar cap around a tracked hole");
  return candidates.sort((left, right) => (
    Math.abs(kernel.getSurfaceArea(left) - expectedArea) - Math.abs(kernel.getSurfaceArea(right) - expectedArea)
  ))[0]!;
}

function representativeExtrusion(
  kernel: OcctKernel,
  positions: Float32Array,
  sections: readonly SliceSection[],
  track: HoleTrack,
  modelBounds: ReturnType<typeof bounds>,
  axisIndex: AxisIndex,
  tolerance: number,
): ShapeHandle {
  const span = modelBounds.upper[axisIndex] - modelBounds.lower[axisIndex];
  const holeArea = track.observations
    .map((observation) => observation.loop.area)
    .sort((left, right) => left - right)[Math.floor(track.observations.length / 2)]!;
  const targetOuterArea = meshVolume(positions) / span + holeArea;
  const representative = [...sections].sort((left, right) => (
    Math.abs(left.outer.area - targetOuterArea) - Math.abs(right.outer.area - targetOuterArea)
  ))[0]!;
  const hole = track.observations[Math.floor(track.observations.length / 2)]!.loop;
  const coordinate = modelBounds.lower[axisIndex];
  const outerWire = segmentedWireForLoop(kernel, representative.outer, coordinate, axisIndex, tolerance);
  let holeWire = wireForLoop(kernel, hole, coordinate, axisIndex, tolerance, isPolygonal(hole, tolerance));
  if (signedArea(representative.outer.points) * signedArea(hole.points) > 0) {
    holeWire = kernel.reverseShape(holeWire);
  }
  const cap = planarCapWithHole(kernel, outerWire, holeWire, representative.outer.area - hole.area);
  const capFaces = kernel.isFace(cap) ? [cap] : kernel.getSubShapes(cap, "face");
  if (capFaces.length !== 1) throw new Error("The representative curved profile did not produce one planar face");
  if (axisIndex === 0) return kernel.extrude(capFaces[0]!, span, 0, 0);
  if (axisIndex === 1) return kernel.extrude(capFaces[0]!, 0, span, 0);
  return kernel.extrude(capFaces[0]!, 0, 0, span);
}

function loftSegmentWithHole(
  kernel: OcctKernel,
  profiles: readonly OuterProfile[],
  track: HoleTrack,
  extent: [number, number],
  axisIndex: AxisIndex,
  tolerance: number,
): ShapeHandle {
  const outerWires = profiles.map((profile) => wireForLoop(
    kernel,
    profile.outer,
    profile.coordinate,
    axisIndex,
    tolerance,
    false,
  ));
  const outerSolid = kernel.loft(outerWires, true, false);
  const polygonal = track.observations.every((observation) => isPolygonal(observation.loop, tolerance));
  const constantSection = trackIsConstant(track, tolerance);
  let lowerHole: ShapeHandle;
  let upperHole: ShapeHandle;
  let holeSolid: ShapeHandle;
  if (constantSection) {
    lowerHole = wireForLoop(kernel, track.observations[0]!.loop, extent[0], axisIndex, tolerance, polygonal);
    upperHole = wireForLoop(kernel, track.observations.at(-1)!.loop, extent[1], axisIndex, tolerance, polygonal);
    holeSolid = kernel.loft([lowerHole, upperHole], true, true);
  } else {
    const holeProfiles = [
      { coordinate: extent[0], loop: track.observations[0]!.loop },
      ...track.observations.map((observation) => ({ coordinate: observation.coordinate, loop: observation.loop })),
      { coordinate: extent[1], loop: track.observations.at(-1)!.loop },
    ].filter((profile, index, all) => index === 0 || Math.abs(profile.coordinate - all[index - 1]!.coordinate) > 1e-10);
    const holeWires = holeProfiles.map((profile) => wireForLoop(
      kernel,
      profile.loop,
      profile.coordinate,
      axisIndex,
      tolerance,
      polygonal,
    ));
    lowerHole = holeWires[0]!;
    upperHole = holeWires.at(-1)!;
    holeSolid = kernel.loft(holeWires, true, false);
  }
  const capEpsilon = Math.max((extent[1] - extent[0]) * 1e-7, 1e-7);
  const outerSides = kernel.getSubShapes(outerSolid, "face")
    .filter((face) => axisSpan(kernel, face, axisIndex) > capEpsilon);
  const innerSides = kernel.getSubShapes(holeSolid, "face")
    .filter((face) => axisSpan(kernel, face, axisIndex) > capEpsilon)
    .map((face) => kernel.reverseShape(face));
  const lowerCapHole = signedArea(profiles[0]!.outer.points) * signedArea(track.observations[0]!.loop.points) > 0
    ? kernel.reverseShape(lowerHole)
    : lowerHole;
  const upperCapHole = signedArea(profiles.at(-1)!.outer.points) * signedArea(track.observations.at(-1)!.loop.points) > 0
    ? kernel.reverseShape(upperHole)
    : upperHole;
  const lowerCap = planarCapWithHole(
    kernel,
    outerWires[0]!,
    lowerCapHole,
    profiles[0]!.outer.area - track.observations[0]!.loop.area,
  );
  const upperCap = planarCapWithHole(
    kernel,
    outerWires.at(-1)!,
    upperCapHole,
    profiles.at(-1)!.outer.area - track.observations.at(-1)!.loop.area,
  );
  const capFaces = [lowerCap, upperCap].flatMap((cap) => (
    kernel.isFace(cap) ? [cap] : kernel.getSubShapes(cap, "face")
  ));
  let result = kernel.sewAndSolidify(
    [...outerSides, ...innerSides, ...capFaces],
    Math.max(tolerance * 0.1, 1e-6),
  );
  if (!kernel.isValid(result) || (!kernel.isSolid(result) && kernel.getSubShapes(result, "solid").length !== 1)) {
    result = kernel.fixFaceOrientations(result);
    if (!kernel.isValid(result)) result = kernel.fixShape(result);
  }
  const solids = kernel.getSubShapes(result, "solid");
  if (!kernel.isValid(result) || (!kernel.isSolid(result) && solids.length !== 1)) {
    throw new Error(
      `The curved fitter could not sew the lofted hole segment into a solid (outer sides ${outerSides.length}, inner sides ${innerSides.length}, solids ${solids.length})`,
    );
  }
  return kernel.isSolid(result) ? result : solids[0]!;
}

function profilesBetween(
  profiles: readonly OuterProfile[],
  lower: OuterProfile,
  upper: OuterProfile,
  epsilon: number,
): OuterProfile[] {
  return [
    lower,
    ...profiles.filter((profile) => (
      profile.coordinate > lower.coordinate + epsilon
      && profile.coordinate < upper.coordinate - epsilon
    )),
    upper,
  ];
}

/**
 * Rebuild a watertight, mostly layered STL as a genuine swept or smooth-loft
 * B-Rep. This is intentionally bounded: arbitrary organic topology must use
 * the native surface-network engine instead of being mislabeled as recovered CAD.
 */
export function reconstructLayeredCurvedShape(
  kernel: OcctKernel,
  positions: Float32Array,
  tolerance: number,
  progress?: (stage: string) => void,
): LayeredCurvedShape {
  if (positions.length === 0 || positions.length % 9 !== 0) throw new Error("Curved reconstruction requires complete STL triangles");
  const { axisIndex, sections } = chooseAxis(positions);
  progress?.(`sections:${sections.length}`);
  const modelBounds = bounds(positions);
  const simplifyTolerance = Math.max(tolerance * 0.35, 1e-4);
  const outerProfiles: OuterProfile[] = [
    { coordinate: modelBounds.lower[axisIndex], outer: sections[0]!.outer },
    ...sections.map((section) => ({ coordinate: section.coordinate, outer: section.outer })),
    { coordinate: modelBounds.upper[axisIndex], outer: sections.at(-1)!.outer },
  ];
  const tracks = trackHoles(sections);
  progress?.(`hole-tracks:${tracks.length}`);
  // A loop observed in only one cross-section is below the sampling proof
  // needed to infer a closed pocket. Preserve only tracks corroborated by at
  // least two independent sections; isolated lettering/detail stays explicit
  // in the approximation evidence instead of becoming invented topology.
  const qualifiedTracks = tracks.filter((track) => track.observations.length >= 2);
  let shape: ShapeHandle;
  let reconstructionMode: LayeredCurvedEvidence["reconstructionMode"] = "smooth-loft";
  const representativeTrack = qualifiedTracks.length === 1
    && qualifiedTracks[0]!.observations.length / sections.length >= 0.8
    ? qualifiedTracks[0]!
    : undefined;
  if (representativeTrack) {
    shape = representativeExtrusion(
      kernel,
      positions,
      sections,
      representativeTrack,
      modelBounds,
      axisIndex,
      simplifyTolerance,
    );
    reconstructionMode = "representative-extrusion";
    progress?.("outer-wires:1");
    progress?.("outer-loft:representative-extrusion");
    progress?.(`hole-tool:1:observations=${representativeTrack.observations.length}:sections=${representativeTrack.observations[0]!.sectionIndex}-${representativeTrack.observations.at(-1)!.sectionIndex}:area=${representativeTrack.observations[0]!.loop.area.toFixed(4)}`);
  // A lone blind/part-depth hole can make a boolean against one large lofted
  // B-spline face extremely expensive. Split the outer loft at the observed
  // hole extent, cut only the intersecting slab, then reunite the slabs. The
  // cutting tool crosses planar slab caps instead of requiring a global
  // B-spline intersection, while the external skin remains genuinely curved.
  } else if (qualifiedTracks.length === 1) {
    const track = qualifiedTracks[0]!;
    const rawExtent = trackBounds(track, sections);
    // When a tracked void stops inside the model, terminate its stitched slab
    // on the last section that actually proves the void is inside the outer
    // profile. The midpoint toward a no-hole section can already lie outside
    // the material, which would make a planar annular cap invalid.
    if (track.observations[0]!.sectionIndex > 0) rawExtent[0] = track.observations[0]!.coordinate;
    if (track.observations.at(-1)!.sectionIndex < sections.length - 1) {
      rawExtent[1] = track.observations.at(-1)!.coordinate;
    }
    const lowerBound = modelBounds.lower[axisIndex];
    const upperBound = modelBounds.upper[axisIndex];
    const extent: [number, number] = [
      Math.max(lowerBound, rawExtent[0]),
      Math.min(upperBound, rawExtent[1]),
    ];
    const epsilon = Math.max((upperBound - lowerBound) * 1e-9, 1e-8);
    const lowerFallback = sections[track.observations[0]!.sectionIndex]!.outer;
    const upperFallback = sections[track.observations.at(-1)!.sectionIndex]!.outer;
    const lowerProfile: OuterProfile = {
      coordinate: extent[0],
      outer: track.observations[0]!.sectionIndex > 0
        ? lowerFallback
        : extent[0] <= lowerBound + epsilon
        ? outerProfiles[0]!.outer
        : outerLoopAt(positions, axisIndex, extent[0], lowerFallback),
    };
    const upperProfile: OuterProfile = {
      coordinate: extent[1],
      outer: track.observations.at(-1)!.sectionIndex < sections.length - 1
        ? upperFallback
        : extent[1] >= upperBound - epsilon
        ? outerProfiles.at(-1)!.outer
        : outerLoopAt(positions, axisIndex, extent[1], upperFallback),
    };
    const segments: ShapeHandle[] = [];
    if (extent[0] > lowerBound + epsilon) {
      segments.push(loftOuterProfiles(
        kernel,
        profilesBetween(outerProfiles, outerProfiles[0]!, lowerProfile, epsilon),
        axisIndex,
        simplifyTolerance,
      ));
    }
    const middleProfiles = profilesBetween(outerProfiles, lowerProfile, upperProfile, epsilon);
    progress?.(`outer-wires:${outerProfiles.length}`);
    progress?.(`outer-loft:segmented=${Number(extent[0] > lowerBound + epsilon) + 1 + Number(extent[1] < upperBound - epsilon)}`);
    progress?.(`hole-tool:1:observations=${track.observations.length}:sections=${track.observations[0]!.sectionIndex}-${track.observations.at(-1)!.sectionIndex}:area=${track.observations[0]!.loop.area.toFixed(4)}`);
    const middle = loftSegmentWithHole(
      kernel,
      middleProfiles,
      track,
      extent,
      axisIndex,
      simplifyTolerance,
    );
    segments.push(middle);
    if (extent[1] < upperBound - epsilon) {
      segments.push(loftOuterProfiles(
        kernel,
        profilesBetween(outerProfiles, upperProfile, outerProfiles.at(-1)!, epsilon),
        axisIndex,
        simplifyTolerance,
      ));
    }
    shape = segments.length === 1 ? segments[0]! : kernel.fuseAll(segments);
  } else {
    shape = loftOuterProfiles(kernel, outerProfiles, axisIndex, simplifyTolerance);
    progress?.(`outer-wires:${outerProfiles.length}`);
    progress?.("outer-loft");
    const tools: ShapeHandle[] = [];
    for (const track of qualifiedTracks) {
      const extent = trackBounds(track, sections);
      if (extent[1] - extent[0] <= simplifyTolerance) continue;
      tools.push(loftLoopTrack(kernel, track.observations, extent, axisIndex, simplifyTolerance));
      progress?.(`hole-tool:${tools.length}:observations=${track.observations.length}:sections=${track.observations[0]!.sectionIndex}-${track.observations.at(-1)!.sectionIndex}:area=${track.observations[0]!.loop.area.toFixed(4)}`);
    }
    if (tools.length > 0) shape = kernel.cutAll(shape, tools);
  }
  progress?.("cut-holes");
  if (!kernel.isValid(shape)) shape = kernel.fixShape(shape);
  if (!kernel.isValid(shape) || (!kernel.isSolid(shape) && kernel.getSubShapes(shape, "solid").length !== 1)) {
    throw new Error("The layered curved loft did not produce one valid OCCT solid");
  }
  return {
    shape,
    evidence: {
      axisIndex,
      sectionCount: sections.length,
      outerProfileCount: reconstructionMode === "representative-extrusion" ? 1 : outerProfiles.length,
      holeTrackCount: qualifiedTracks.length,
      sourceTriangleCount: positions.length / 9,
      reconstructionMode,
    },
  };
}
