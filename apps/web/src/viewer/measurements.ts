export type Point3 = readonly [number, number, number];
export type MeasurementMode = "distance" | "angle" | "radius";

const GEOMETRY_EPSILON = 1e-12;

function subtract(a: Point3, b: Point3): Point3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a: Point3, b: Point3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function length(value: Point3): number {
  return Math.hypot(value[0], value[1], value[2]);
}

export function requiredMeasurementPoints(mode: MeasurementMode): number {
  return mode === "distance" ? 2 : 3;
}

export function pointDistance(a: Point3, b: Point3): number {
  return length(subtract(a, b));
}

export function angleDegrees(a: Point3, vertex: Point3, c: Point3): number | null {
  const first = subtract(a, vertex);
  const second = subtract(c, vertex);
  const denominator = length(first) * length(second);
  if (!Number.isFinite(denominator) || denominator <= GEOMETRY_EPSILON) return null;
  const cosine = Math.max(-1, Math.min(1, dot(first, second) / denominator));
  return Math.acos(cosine) * 180 / Math.PI;
}

export function circumradius(a: Point3, b: Point3, c: Point3): number | null {
  const ab = subtract(b, a);
  const ac = subtract(c, a);
  const cross: Point3 = [
    ab[1] * ac[2] - ab[2] * ac[1],
    ab[2] * ac[0] - ab[0] * ac[2],
    ab[0] * ac[1] - ab[1] * ac[0],
  ];
  const twiceArea = length(cross);
  const sideA = pointDistance(b, c);
  const sideB = pointDistance(a, c);
  const sideC = pointDistance(a, b);
  const scale = Math.max(sideA, sideB, sideC);
  if (!Number.isFinite(twiceArea) || twiceArea <= scale * scale * GEOMETRY_EPSILON) return null;
  return sideA * sideB * sideC / (2 * twiceArea);
}

export function measurementLabel(
  mode: MeasurementMode,
  points: readonly Point3[],
  units: string,
): string | null {
  if (points.length < requiredMeasurementPoints(mode)) return null;
  if (mode === "distance") return `${pointDistance(points[0]!, points[1]!).toFixed(3)} ${units}`;
  if (mode === "angle") {
    const value = angleDegrees(points[0]!, points[1]!, points[2]!);
    return value === null ? "Undefined angle" : `${value.toFixed(3)}°`;
  }
  const value = circumradius(points[0]!, points[1]!, points[2]!);
  return value === null ? "Undefined radius" : `R ${value.toFixed(3)} ${units}`;
}
