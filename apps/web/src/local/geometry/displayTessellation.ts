import type { BoundingBox, EdgeData, TessellateOptions } from "occt-wasm";

import type { BrowserEdgeLines } from "./types";

export const DISPLAY_RELATIVE_LINEAR_DEFLECTION = 2.5e-4;
export const DISPLAY_ANGULAR_DEFLECTION = Math.PI / 180;
export const DISPLAY_EDGE_ANGULAR_DEFLECTION = DISPLAY_ANGULAR_DEFLECTION;
export const MAX_DISPLAY_EDGE_SEGMENTS = 200_000;

export interface DisplayTessellationOptions {
  mesh: Required<Pick<TessellateOptions, "linearDeflection" | "angularDeflection">>;
  edgeAngularDeflection: number;
  modelDiagonal: number;
}

/**
 * Select a bounded result-view LOD from exact OCCT bounds.
 *
 * The maximum values retain stricter project-specific settings.  The relative
 * chordal term makes display quality independent of the project's chosen unit
 * system, while the angular cap keeps small circles and holes from inheriting a
 * large model's looser absolute deflection.
 */
export function displayTessellationOptions(
  bounds: BoundingBox,
  maximumLinearDeflection: number,
  maximumAngularDeflection: number,
): DisplayTessellationOptions {
  if (!Number.isFinite(maximumLinearDeflection) || maximumLinearDeflection <= 0) {
    throw new Error("Display linear deflection must be finite and positive");
  }
  if (!Number.isFinite(maximumAngularDeflection) || maximumAngularDeflection <= 0) {
    throw new Error("Display angular deflection must be finite and positive");
  }
  const diagonal = Math.hypot(
    bounds.xmax - bounds.xmin,
    bounds.ymax - bounds.ymin,
    bounds.zmax - bounds.zmin,
  );
  const scaledLinear = Number.isFinite(diagonal) && diagonal > 0
    ? Math.max(diagonal * DISPLAY_RELATIVE_LINEAR_DEFLECTION, 1e-9)
    : maximumLinearDeflection;
  return {
    mesh: {
      linearDeflection: Math.min(maximumLinearDeflection, scaledLinear),
      angularDeflection: Math.min(maximumAngularDeflection, DISPLAY_ANGULAR_DEFLECTION),
    },
    edgeAngularDeflection: Math.min(
      maximumAngularDeflection,
      DISPLAY_EDGE_ANGULAR_DEFLECTION,
    ),
    modelDiagonal: Number.isFinite(diagonal) && diagonal > 0 ? diagonal : 0,
  };
}

/**
 * Convert OCCT's exact-curve polylines to a GL LINES index buffer.
 *
 * OCCT reports edge group offsets/counts in float coordinates, not vertices.
 * A global segment cap keeps pathological topology bounded; when reached, each
 * polyline is sampled at the same stride and still retains both endpoints.
 */
export function edgeLinesFromWireframe(
  data: EdgeData,
  maximumSegments = MAX_DISPLAY_EDGE_SEGMENTS,
): BrowserEdgeLines {
  if (!Number.isSafeInteger(maximumSegments) || maximumSegments < 1) {
    throw new Error("Display edge segment limit must be a positive safe integer");
  }
  const groups: Array<{ start: number; count: number }> = [];
  let rawSegments = 0;
  for (let group = 0; group + 2 < data.edgeGroups.length; group += 3) {
    const floatStart = data.edgeGroups[group]!;
    const floatCount = data.edgeGroups[group + 1]!;
    if (
      floatStart < 0
      || floatCount < 6
      || floatStart % 3 !== 0
      || floatCount % 3 !== 0
      || floatStart + floatCount > data.points.length
    ) {
      continue;
    }
    const count = floatCount / 3;
    groups.push({ start: floatStart / 3, count });
    rawSegments += count - 1;
  }
  if (groups.length === 0) {
    return {
      positions: new Float32Array(),
      indices: new Uint32Array(),
      segmentCount: 0,
    };
  }
  if (groups.length > maximumSegments) {
    return {
      positions: new Float32Array(),
      indices: new Uint32Array(),
      segmentCount: 0,
    };
  }

  const sampledSegmentCount = (stride: number): number => {
    let total = 0;
    for (const group of groups) {
      total += Math.ceil((group.count - 1) / stride);
      if (total > maximumSegments) return total;
    }
    return total;
  };
  let lower = Math.max(1, Math.ceil(rawSegments / maximumSegments));
  let upper = 1;
  for (const group of groups) upper = Math.max(upper, group.count - 1);
  while (lower < upper) {
    const middle = lower + Math.floor((upper - lower) / 2);
    if (sampledSegmentCount(middle) <= maximumSegments) upper = middle;
    else lower = middle + 1;
  }
  const stride = lower;
  const positions: number[] = [];
  const indices: number[] = [];
  for (const group of groups) {
    const sampled: number[] = [];
    for (let point = 0; point < group.count - 1; point += stride) sampled.push(point);
    sampled.push(group.count - 1);
    const base = positions.length / 3;
    for (const point of sampled) {
      const offset = (group.start + point) * 3;
      positions.push(data.points[offset]!, data.points[offset + 1]!, data.points[offset + 2]!);
    }
    for (let point = 0; point < sampled.length - 1; point += 1) {
      indices.push(base + point, base + point + 1);
    }
  }
  return {
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
    segmentCount: indices.length / 2,
  };
}
