import { Matrix, SingularValueDecomposition } from "ml-matrix";

import type { Vec2 } from "./sections";

export interface BrowserBSplinePrimitive {
  kind: "bspline";
  start: Vec2;
  end: Vec2;
  degree: number;
  controlPoints: Vec2[];
  rms: number;
  maximum: number;
  condition: number;
}

export interface BrowserRegularPolygon {
  sideCount: number;
  center: Vec2;
  circumdiameter: number;
  points: Vec2[];
  clockwise: boolean;
  maximumRadialResidual: number;
  maximumAngularResidualDeg: number;
}

function openUniformKnots(controlPointCount: number, degree: number): number[] {
  const interiorCount = controlPointCount - degree - 1;
  return [
    ...Array.from({ length: degree + 1 }, () => 0),
    ...Array.from({ length: interiorCount }, (_value, index) => (index + 1) / (interiorCount + 1)),
    ...Array.from({ length: degree + 1 }, () => 1),
  ];
}

function basisRow(parameterValue: number, controlPointCount: number, degree: number, knots: readonly number[]): number[] {
  const parameter = parameterValue >= 1 ? 1 - Number.EPSILON : Math.max(0, parameterValue);
  let values: number[] = Array.from({ length: controlPointCount }, (_value, index) => (
    knots[index]! <= parameter && parameter < knots[index + 1]! ? 1 : 0
  ));
  for (let order = 1; order <= degree; order += 1) {
    values = values.map((_value, index) => {
      const leftDenominator = knots[index + order]! - knots[index]!;
      const rightDenominator = knots[index + order + 1]! - knots[index + 1]!;
      const left = leftDenominator > 0 ? (parameter - knots[index]!) / leftDenominator * values[index]! : 0;
      const right = rightDenominator > 0 && index + 1 < values.length
        ? (knots[index + order + 1]! - parameter) / rightDenominator * values[index + 1]!
        : 0;
      return left + right;
    });
  }
  if (parameterValue >= 1) {
    values.fill(0);
    values[controlPointCount - 1] = 1;
  }
  return values;
}

function evaluateBSpline(controlPoints: readonly Vec2[], degree: number, parameter: number): Vec2 {
  const basis = basisRow(parameter, controlPoints.length, degree, openUniformKnots(controlPoints.length, degree));
  return controlPoints.reduce<Vec2>((result, point, index) => [
    result[0] + point[0] * basis[index]!,
    result[1] + point[1] * basis[index]!,
  ], [0, 0]);
}

function fitControls(points: readonly Vec2[], parameters: readonly number[], count: number, degree: number): { controls: Vec2[]; condition: number } {
  const knots = openUniformKnots(count, degree);
  const rows = parameters.map((parameter) => basisRow(parameter, count, degree, knots));
  const first = points[0]!; const last = points.at(-1)!;
  const interiorRows = rows.map((row) => row.slice(1, -1));
  const rightHand = rows.map((row, index) => [
    points[index]![0] - row[0]! * first[0] - row.at(-1)! * last[0],
    points[index]![1] - row[0]! * first[1] - row.at(-1)! * last[1],
  ]);
  const decomposition = new SingularValueDecomposition(new Matrix(interiorRows), { autoTranspose: true });
  const solved = decomposition.solve(new Matrix(rightHand));
  const controls: Vec2[] = [first];
  for (let row = 0; row < solved.rows; row += 1) controls.push([solved.get(row, 0), solved.get(row, 1)]);
  controls.push(last);
  return { controls, condition: decomposition.condition };
}

function squaredDistance(left: Vec2, right: Vec2): number {
  return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2;
}

function goldenMinimum(objective: (value: number) => number, lowerValue: number, upperValue: number): number {
  const ratio = (Math.sqrt(5) - 1) / 2;
  let lower = lowerValue; let upper = upperValue;
  let left = upper - ratio * (upper - lower); let right = lower + ratio * (upper - lower);
  let leftValue = objective(left); let rightValue = objective(right);
  for (let iteration = 0; iteration < 80 && upper - lower > 1e-12; iteration += 1) {
    if (leftValue <= rightValue) {
      upper = right; right = left; rightValue = leftValue; left = upper - ratio * (upper - lower); leftValue = objective(left);
    } else {
      lower = left; left = right; leftValue = rightValue; right = lower + ratio * (upper - lower); rightValue = objective(right);
    }
  }
  return (lower + upper) / 2;
}

function fitOne(points: readonly Vec2[], count: number, degree: number): BrowserBSplinePrimitive {
  const chordLengths = points.slice(1).map((point, index) => Math.sqrt(squaredDistance(point, points[index]!)));
  const total = chordLengths.reduce((sum, value) => sum + value, 0);
  if (!(total > 1e-12)) throw new Error("B-spline evidence has zero chord length");
  const parameters = [0];
  for (const chord of chordLengths) parameters.push(parameters.at(-1)! + chord / total);
  let controls: Vec2[] = [];
  let previousRms = Number.POSITIVE_INFINITY;
  for (let iteration = 0; iteration < 50; iteration += 1) {
    controls = fitControls(points, parameters, count, degree).controls;
    const previous = [...parameters];
    for (let index = 1; index < points.length - 1; index += 1) {
      const lower = previous[index - 1]! + 1e-12;
      const upper = previous[index + 1]! - 1e-12;
      parameters[index] = goldenMinimum(
        (parameter) => squaredDistance(evaluateBSpline(controls, degree, parameter), points[index]!),
        lower,
        upper,
      );
    }
    const residuals = points.map((point, index) => Math.sqrt(squaredDistance(evaluateBSpline(controls, degree, parameters[index]!), point)));
    const rms = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / residuals.length);
    if (iteration >= 15 && Math.abs(previousRms - rms) <= 1e-10) break;
    previousRms = rms;
  }
  const finalFit = fitControls(points, parameters, count, degree);
  controls = finalFit.controls;
  const residuals = points.map((point, index) => Math.sqrt(squaredDistance(evaluateBSpline(controls, degree, parameters[index]!), point)));
  return {
    kind: "bspline",
    start: points[0]!,
    end: points.at(-1)!,
    degree,
    controlPoints: controls,
    rms: Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / residuals.length),
    maximum: Math.max(...residuals),
    condition: finalFit.condition,
  };
}

export function fitBoundedBSpline(
  points: readonly Vec2[],
  rmsTolerance: number,
  maximumTolerance: number,
): BrowserBSplinePrimitive {
  if (points.length < 4 || points.length > 4096) throw new Error("B-spline evidence is outside the bounded point count");
  if (points.some((point) => !point.every(Number.isFinite))) throw new Error("B-spline evidence contains non-finite coordinates");
  const fits = Array.from({ length: 5 }, (_value, index) => fitOne(points, index + 4, 3));
  const accepted = fits.filter((fit) => fit.rms <= rmsTolerance && fit.maximum <= maximumTolerance && Number.isFinite(fit.condition));
  if (accepted.length === 0) {
    const best = fits.sort((left, right) => left.rms + 0.25 * left.maximum - (right.rms + 0.25 * right.maximum))[0]!;
    throw new Error(`Bounded B-spline fit exceeds residual limits: rms=${best.rms}, max=${best.maximum}`);
  }
  return accepted.sort((left, right) => (
    left.rms + 0.25 * left.maximum + 0.0025 * (left.controlPoints.length - 4)
    - (right.rms + 0.25 * right.maximum + 0.0025 * (right.controlPoints.length - 4))
  ))[0]!;
}

function wrapAngle(value: number): number {
  return Math.atan2(Math.sin(value), Math.cos(value));
}

export function fitRegularPolygon(points: readonly Vec2[], tolerance: number): BrowserRegularPolygon {
  if (points.length < 3 || points.length > 12) throw new Error("Regular polygon has an unsupported side count");
  const center: Vec2 = [
    points.reduce((sum, point) => sum + point[0], 0) / points.length,
    points.reduce((sum, point) => sum + point[1], 0) / points.length,
  ];
  const radial = points.map((point) => [point[0] - center[0], point[1] - center[1]] as Vec2);
  const radii = radial.map((point) => Math.hypot(...point));
  const radius = radii.reduce((sum, value) => sum + value, 0) / radii.length;
  const maximumRadialResidual = Math.max(...radii.map((value) => Math.abs(value - radius)));
  const area = points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length]!;
    return sum + point[0] * next[1] - point[1] * next[0];
  }, 0) / 2;
  const clockwise = area < 0;
  const direction = clockwise ? -1 : 1;
  const phase = Math.atan2(radial[0]![1], radial[0]![0]);
  const maximumAngularResidualDeg = Math.max(...radial.map((point, index) => (
    Math.abs(wrapAngle(Math.atan2(point[1], point[0]) - (phase + direction * 2 * Math.PI * index / points.length))) * 180 / Math.PI
  )));
  if (maximumRadialResidual > tolerance || maximumAngularResidualDeg > 1) {
    throw new Error(`Loop is not regular: radial=${maximumRadialResidual}, angular=${maximumAngularResidualDeg}`);
  }
  const measuredDiameter = radius * 2;
  const nominal = Math.round(measuredDiameter / 0.5) * 0.5;
  const diameter = Math.abs(nominal - measuredDiameter) <= tolerance ? nominal : measuredDiameter;
  return {
    sideCount: points.length,
    center,
    circumdiameter: diameter,
    clockwise,
    maximumRadialResidual,
    maximumAngularResidualDeg,
    points: Array.from({ length: points.length }, (_value, index) => [
      center[0] + diameter / 2 * Math.cos(phase + direction * 2 * Math.PI * index / points.length),
      center[1] + diameter / 2 * Math.sin(phase + direction * 2 * Math.PI * index / points.length),
    ]),
  };
}
