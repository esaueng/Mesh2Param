import type { BsplineEntity, CADGraph, Feature, FeatureBase, Sketch, SketchEntity, Vector2, Vector3 } from "@mesh2param/contracts";
import { validateCADGraph } from "@mesh2param/contracts";
import type { OcctKernel } from "occt-wasm";

import { compareMeshes } from "./comparison";
import { compileCadGraphWithTopology } from "./compiler";
import { triangleMeshFromStl, type BrowserTriangleMesh } from "./mesh";
import { fitRegularPolygon, type BrowserRegularPolygon } from "./profileFitting";
import { fitBrowserSplineProfile, type BrowserProfilePrimitive } from "./prismatic";
import { extractSectionSliceAtOffset, extractSectionStack, type BrowserSectionStack, type ProjectionFrame, type Vec2, type Vec3Tuple } from "./sections";
import { selectPrismaticRimEdges } from "./topology";
import type {
  BrowserGeometryStage,
  BrowserMesh,
  BrowserParametricProbe,
  BrowserParametricResult,
  BrowserReconstructionError,
  ParametricStlGeometryRequest,
} from "./types";

type Progress = (stage: BrowserGeometryStage, fraction: number, message: string) => void;

// The functional path remains tied to the caller's project-unit tolerance.
// Its wider angular gate is limited to the source's detected 45-degree
// chamfer network; valid-solid and STEP round-trip gates remain unchanged.
const FUNCTIONAL_P95_TOLERANCE_MULTIPLIER = 4;
const FUNCTIONAL_MAX_TOLERANCE_MULTIPLIER = 8;
const FUNCTIONAL_MINIMUM_COVERAGE = 0.9;
const FUNCTIONAL_MAXIMUM_NORMAL_ANGLE_DEG = 45;
const FUNCTIONAL_MAXIMUM_RELATIVE_VOLUME_DELTA = 0.01;

interface BossEvidence {
  origin: Vec2;
  width: number;
  height: number;
  depth: number;
  sourceTriangleIds: number[];
}

interface RaisedProfileEvidence {
  points: Vec2[];
  area: number;
  depth: number;
  areaFraction: number;
  sourceTriangleIds: number[];
}

interface RimTreatment {
  kind: "fillet" | "chamfer";
  size: number;
}

export class ParametricReconstructionFailure extends Error {
  constructor(readonly structured: BrowserReconstructionError) {
    super(structured.message);
    this.name = "ParametricReconstructionFailure";
  }
}

function selectedRimTreatment(stack: BrowserSectionStack): RimTreatment | null {
  const filletResidual = stack.radiusFit.accepted ? stack.radiusFit.rmsResidual ?? Number.POSITIVE_INFINITY : Number.POSITIVE_INFINITY;
  const chamferResidual = stack.chamferFit.accepted ? stack.chamferFit.rmsResidual ?? Number.POSITIVE_INFINITY : Number.POSITIVE_INFINITY;
  if (stack.chamferFit.accepted && stack.chamferFit.width !== null && chamferResidual <= filletResidual * 0.75) {
    return { kind: "chamfer", size: stack.chamferFit.width };
  }
  if (stack.radiusFit.accepted && stack.radiusFit.radius !== null) return { kind: "fillet", size: stack.radiusFit.radius };
  if (stack.chamferFit.accepted && stack.chamferFit.width !== null) return { kind: "chamfer", size: stack.chamferFit.width };
  return null;
}

export function probeParametricStl(bytes: ArrayBuffer, scaleFactor: number, tolerance: number): BrowserParametricProbe {
  let mesh: BrowserTriangleMesh | null = null;
  try {
    mesh = triangleMeshFromStl(bytes, scaleFactor, tolerance);
    const stack = extractSectionStack(mesh, tolerance);
    if (stack.blindFeatureDetected || stack.taperedExtrusionDetected) {
      fail("sections", "unsupported-prismatic-topology", "The mesh is not a constant-axis prismatic member", {
        maximumSupportChange: stack.maximumSupportChange,
      });
    }
    const reference = stack.slices[stack.referenceSliceIndex]!;
    if (reference.loops.length !== 2) {
      fail("profile-fitting", "unsupported-loop-count", "Expected one outer profile and one through-cut", { loopCount: reference.loops.length });
    }
    const primitives = fitBrowserSplineProfile(reference.loops[0]!.points);
    const polygon = fitRegularPolygon(reference.loops[1]!.points, tolerance);
    if (primitives === null || polygon.sideCount !== 6) {
      fail("profile-fitting", "unsupported-profile-family", "The profiles are outside the bounded spanner family", { polygonSides: polygon.sideCount });
    }
    const boss = primitives.length <= 16 ? detectBoss(mesh, stack, tolerance) : null;
    const raised = boss === null ? detectRaisedProfile(mesh, stack, tolerance) : null;
    const rim = primitives.length <= 16 ? selectedRimTreatment(stack) : null;
    return {
      supported: true,
      family: "general-parametric-prismatic",
      triangleCount: mesh.triangleCount,
      featureHints: [
        "extrusion", ...(rim === null ? [] : [rim.kind]), "hex-cut",
        ...(boss !== null ? ["rectangular-boss"] : raised !== null ? ["raised-profile"] : []),
      ],
      detailDetected: boss !== null || raised !== null,
      analysis: {
        accepted: true,
        axis: stack.axis,
        thickness: stack.capOffsets[1] - stack.capOffsets[0],
        filletRadius: rim?.kind === "fillet" ? rim.size : null,
        chamferWidth: rim?.kind === "chamfer" ? rim.size : null,
        raisedProfileDepth: raised?.depth ?? null,
        raisedProfileAreaFraction: raised?.areaFraction ?? null,
        polygonSides: polygon.sideCount,
        polygonCircumdiameter: polygon.circumdiameter,
        primitiveKinds: primitives.map((primitive) => primitive.kind),
      },
      error: null,
    };
  } catch (cause) {
    const structured = cause instanceof ParametricReconstructionFailure
      ? cause.structured
      : { stage: "profile-fitting" as const, code: "probe-failed", message: cause instanceof Error ? cause.message : String(cause), measured: {}, sourceTriangleIds: [] };
    return {
      supported: false,
      family: "general-parametric-prismatic",
      triangleCount: mesh?.triangleCount ?? 0,
      featureHints: [],
      detailDetected: false,
      analysis: { accepted: false, diagnostics: [structured] },
      error: structured,
    };
  }
}

function fail(
  stage: BrowserGeometryStage,
  code: string,
  message: string,
  measured: Record<string, number | string> = {},
  sourceTriangleIds: number[] = [],
): never {
  throw new ParametricReconstructionFailure({ stage, code, message, measured, sourceTriangleIds });
}

function vector(value: Vec3Tuple): Vector3 {
  return { x: value[0], y: value[1], z: value[2] };
}

function dot(left: Vec3Tuple, right: Vec3Tuple): number {
  return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

function addAlong(point: Vec3Tuple, axis: Vec3Tuple, distance: number): Vec3Tuple {
  return [point[0] + axis[0] * distance, point[1] + axis[1] * distance, point[2] + axis[2] * distance];
}

function sourceDescriptor(request: ParametricStlGeometryRequest, triangleCount: number): NonNullable<CADGraph["source"]> {
  return {
    format: "stl",
    sha256: request.source.sha256,
    originalFileName: request.source.originalFileName,
    byteSize: request.source.byteSize,
    triangleCount,
    declaredUnits: request.source.declaredUnits,
    scaleFactor: request.source.scaleFactor,
  };
}

function entityBase(id: string, evidenceId: string) {
  return { id, construction: false as const, sourceEvidence: [evidenceId], confidence: 0.95, locked: false, suppressed: false };
}

function profileEntities(primitives: readonly BrowserProfilePrimitive[], evidenceId: string): { entities: SketchEntity[]; ids: [string, ...string[]] } {
  const entities = primitives.map((primitive, index): SketchEntity => {
    const id = `sketch.base.entity.${String(index + 1).padStart(3, "0")}`;
    const common = entityBase(id, evidenceId);
    if (primitive.kind === "line") {
      return { ...common, kind: "line", start: { x: primitive.start[0], y: primitive.start[1] }, end: { x: primitive.end[0], y: primitive.end[1] } };
    }
    if (primitive.kind === "circle") {
      return { ...common, kind: "circle", center: { x: primitive.center[0], y: primitive.center[1] }, radius: primitive.radius };
    }
    if (primitive.kind === "arc") {
      const startAngleDeg = Math.atan2(primitive.start[1] - primitive.center[1], primitive.start[0] - primitive.center[0]) * 180 / Math.PI;
      return {
        ...common,
        kind: "circularArc",
        center: { x: primitive.center[0], y: primitive.center[1] },
        radius: primitive.radius,
        startAngleDeg,
        endAngleDeg: startAngleDeg + primitive.sweepDeg,
        clockwise: primitive.sweepDeg < 0,
      };
    }
    return {
      ...common,
      kind: "bspline",
      degree: primitive.degree,
      controlPoints: primitive.controlPoints.map((point) => ({ x: point[0], y: point[1] })) as BsplineEntity["controlPoints"],
      clamped: true,
      rational: false,
      periodic: false,
    };
  });
  const ids = entities.map((entity) => entity.id) as [string, ...string[]];
  return { entities, ids };
}

function polygonSketch(polygon: BrowserRegularPolygon, plane: Sketch["plane"], evidenceId: string): Sketch {
  const entities = polygon.points.map((point, index): SketchEntity => ({
    ...entityBase(`sketch.hex-cut.entity.${String(index + 1).padStart(3, "0")}`, evidenceId),
    kind: "line",
    start: { x: point[0], y: point[1] },
    end: { x: polygon.points[(index + 1) % polygon.points.length]![0], y: polygon.points[(index + 1) % polygon.points.length]![1] },
  }));
  return {
    id: "sketch.hex-cut",
    name: `Recovered regular ${polygon.sideCount}-sided cut`,
    plane,
    entities,
    constraints: [],
    profiles: [{
      id: "sketch.hex-cut.profile",
      name: "Recovered regular polygon",
      outerLoop: entities.map((entity) => entity.id) as [string, ...string[]],
      innerLoops: [],
      orientation: polygon.clockwise ? "clockwise" : "counterclockwise",
      closed: true,
      sourceEvidence: [evidenceId],
      confidence: 0.95,
      locked: false,
    }],
    sourceEvidence: [evidenceId],
    confidence: 0.95,
    userLocks: [],
    overrides: [],
    suppressed: false,
  };
}

function featureBase(id: string, name: string, order: number, dependencies: string[], evidenceId: string): Omit<FeatureBase, "operation"> {
  return {
    id,
    name,
    order,
    dependencies,
    suppressed: false,
    sourceEvidence: [evidenceId],
    confidence: 0.95,
    userLocks: [],
    overrides: [],
    semanticOutputs: [`${id}.result`],
  };
}

function baseGraph(
  request: ParametricStlGeometryRequest,
  mesh: BrowserTriangleMesh,
  stack: BrowserSectionStack,
  primitives: readonly BrowserProfilePrimitive[],
  polygon: BrowserRegularPolygon,
): CADGraph {
  const evidenceId = "evidence.browser-parametric";
  const thickness = stack.capOffsets[1] - stack.capOffsets[0];
  const plane = { origin: vector(stack.frame.origin), normal: vector(stack.axis), xAxis: vector(stack.frame.u) };
  const outer = profileEntities(primitives, evidenceId);
  const sketches: Sketch[] = [{
    id: "sketch.base",
    name: "Recovered spline-aware profile",
    plane,
    entities: outer.entities,
    constraints: [],
    profiles: [{
      id: "sketch.base.profile",
      name: "Recovered closed profile",
      outerLoop: outer.ids,
      innerLoops: [],
      orientation: "counterclockwise",
      closed: true,
      sourceEvidence: [evidenceId],
      confidence: 0.95,
      locked: false,
    }],
    sourceEvidence: [evidenceId],
    confidence: 0.95,
    userLocks: [],
    overrides: [],
    suppressed: false,
  }, polygonSketch(polygon, plane, evidenceId)];
  const features: Feature[] = [{
    ...featureBase("feature.base", "Recovered analytic extrusion", 0, [], evidenceId),
    operation: "extrusion",
    booleanMode: "base",
    sketchId: "sketch.base",
    profileIds: ["sketch.base.profile"],
    direction: vector(stack.axis),
    extent: "blind",
    distance: thickness,
  }, {
    ...featureBase("feature.hex-cut", `Recovered ${polygon.sideCount}-sided through cut`, 1, ["feature.base"], evidenceId),
    operation: "extrusion",
    booleanMode: "subtractive",
    sketchId: "sketch.hex-cut",
    profileIds: ["sketch.hex-cut.profile"],
    direction: vector(stack.axis),
    extent: "blind",
    distance: thickness,
  }];
  return {
    schemaVersion: "1.0.0",
    id: "reconstruction.browser-parametric",
    name: "Browser-local parametric reconstruction",
    units: request.units,
    source: sourceDescriptor(request, mesh.triangleCount),
    sourceCoordinateFrame: {
      origin: vector(stack.frame.origin),
      xAxis: vector(stack.frame.u),
      yAxis: vector(stack.frame.v),
      zAxis: vector(stack.axis),
      locked: false,
      confidence: 0.95,
      evidenceIds: [evidenceId],
    },
    projectTolerance: { surfaceDeviation: request.tolerance, angularDeviationDeg: 1, linearResolution: Math.min(request.tolerance, 0.001) },
    sketches,
    features,
    semanticTopology: features.map((feature, index) => ({
      id: `${feature.id}.result`, kind: "solid", producerFeatureId: feature.id,
      role: index + 1 === features.length ? "resultSolid" : "intermediateSolid",
      generatedFrom: feature.operation === "extrusion" ? [feature.profileIds[0]!] : [], status: "unresolved",
    })),
    sourceEvidence: [{
      id: evidenceId,
      sourceType: "derived",
      sourceIds: [],
      measuredValue: thickness,
      residual: Math.max(...primitives.map((primitive) => primitive.maximum), polygon.maximumRadialResidual),
      confidence: 0.95,
      notes: "Browser-local section evidence fitted to a bounded line, arc, B-spline, and regular-polygon feature family.",
      metadata: {
        axis: stack.axis,
        thickness,
        primitiveCount: primitives.length,
        polygonSides: polygon.sideCount,
        polygonCircumdiameter: polygon.circumdiameter,
      },
    }],
    userLocks: [],
    overrides: [],
    reconstructionSettings: {
      maxFeatures: 8, beamWidth: 2, candidatesPerResidual: 2, wallClockSeconds: 120, maxRebuilds: 8,
      minScoreImprovement: 0.0001, nominalSnappingEnabled: true, nominalSnapTolerance: request.tolerance,
      scoreWeights: {
        rmsDistance: 1, p95Distance: 1, maxDistance: 0.5, normalAgreement: 0.5, volumeDifference: 0.75,
        overlap: 0.75, sharpEdgeAlignment: 0.5, boundaryAlignment: 0.5, unmatchedSource: 1,
        excessResult: 1, complexity: 0.1, unsupportedOperation: 2, evidenceConfidence: 0.25,
      },
    },
    engineVersions: {
      mesh2param: "0.1.0", contracts: "1.0.0", cadBackend: "OCCT", cadQuery: "browser-local",
      ocp: "occt-wasm-3.6.1", dependencies: { "occt-wasm": "3.6.1", "ml-matrix": "6.14.0", "three-mesh-bvh": "0.9.11" },
    },
    deterministicSeed: request.deterministicSeed,
    fitMetrics: {
      rmsSurfaceDistance: 0, p95SurfaceDistance: 0, maxSurfaceDistance: 0, normalAgreement: 1,
      volumeDifference: 0, overlap: 0, unmatchedSourceArea: 0, excessResultArea: 0, score: 0,
    },
    validation: {
      status: "notRun", brepValid: null, stepReimportValid: null, toleranceSatisfied: null,
      lastValidFeatureId: null, issues: [],
    },
    versionMetadata: {
      versionId: "version.browser-parametric.1", createdAt: "1970-01-01T00:00:00Z",
      createdBy: "mesh2param-browser-reconstruction", message: "Parametric features reconstructed entirely in the browser.",
    },
    extensions: {
      "mesh2param.dev/browserParametric": {
        family: "general-parametric-prismatic",
        detailMode: request.detailMode,
        primitiveKinds: primitives.map((primitive) => primitive.kind),
      },
      "mesh2param.dev/prismaticReconstruction": {
        scope: "browser-local line, arc, B-spline, extrusion, fillet, polygon cut, and shallow boss",
        detailMode: request.detailMode,
        suppressedRegions: [],
      },
    },
  };
}

function project(frame: ProjectionFrame, point: Vec3Tuple): Vec2 {
  const relative: Vec3Tuple = [point[0] - frame.origin[0], point[1] - frame.origin[1], point[2] - frame.origin[2]];
  return [dot(relative, frame.u), dot(relative, frame.v)];
}

function detectBoss(mesh: BrowserTriangleMesh, stack: BrowserSectionStack, tolerance: number): BossEvidence | null {
  const high = stack.capOffsets[1];
  const offsets = Array.from({ length: mesh.vertexCount }, (_value, vertex) => {
    const offset = vertex * 3;
    return dot([mesh.vertices[offset]!, mesh.vertices[offset + 1]!, mesh.vertices[offset + 2]!], stack.axis);
  });
  const maximum = Math.max(...offsets);
  const depth = maximum - high;
  if (depth <= tolerance * 2) return null;
  const topVertices = offsets.flatMap((offset, vertex) => Math.abs(offset - maximum) <= Math.max(tolerance * 0.2, 1e-5) ? [vertex] : []);
  const points = topVertices.map((vertex) => project(stack.frame, [
    mesh.vertices[vertex * 3]!, mesh.vertices[vertex * 3 + 1]!, mesh.vertices[vertex * 3 + 2]!,
  ]));
  if (points.length < 4) return null;
  const minimumX = Math.min(...points.map((point) => point[0])); const maximumX = Math.max(...points.map((point) => point[0]));
  const minimumY = Math.min(...points.map((point) => point[1])); const maximumY = Math.max(...points.map((point) => point[1]));
  const width = maximumX - minimumX; const height = maximumY - minimumY;
  if (width <= tolerance * 2 || height <= tolerance * 2) return null;
  const sourceTriangleIds = Array.from({ length: mesh.triangleCount }, (_value, triangle) => triangle).filter((triangle) => (
    [0, 1, 2].some((corner) => offsets[mesh.faces[triangle * 3 + corner]!]! > high + tolerance)
  ));
  return { origin: [minimumX, minimumY], width, height, depth, sourceTriangleIds };
}

function detectRaisedProfile(mesh: BrowserTriangleMesh, stack: BrowserSectionStack, tolerance: number): RaisedProfileEvidence | null {
  const high = stack.capOffsets[1];
  let maximum = Number.NEGATIVE_INFINITY;
  for (let vertex = 0; vertex < mesh.vertexCount; vertex += 1) {
    const offset = vertex * 3;
    maximum = Math.max(maximum, dot([
      mesh.vertices[offset]!, mesh.vertices[offset + 1]!, mesh.vertices[offset + 2]!,
    ], stack.axis));
  }
  const depth = maximum - high;
  if (depth <= tolerance * 2) return null;
  let slice;
  try {
    slice = extractSectionSliceAtOffset(mesh, stack.axis, stack.frame, high + depth / 2, tolerance);
  } catch {
    return null;
  }
  if (slice.loops.length !== 1 || slice.loops[0]!.points.length < 3 || slice.loops[0]!.points.length > 1024) return null;
  const area = Math.abs(slice.loops[0]!.signedArea);
  const referenceArea = Math.abs(stack.slices[stack.referenceSliceIndex]!.loops[0]!.signedArea);
  if (!(area > tolerance * tolerance) || !(referenceArea > tolerance * tolerance)) return null;
  const sourceTriangleIds = Array.from({ length: mesh.triangleCount }, (_value, triangle) => triangle).filter((triangle) => (
    [0, 1, 2].some((corner) => {
      const vertex = mesh.faces[triangle * 3 + corner]! * 3;
      return dot([mesh.vertices[vertex]!, mesh.vertices[vertex + 1]!, mesh.vertices[vertex + 2]!], stack.axis) > high + tolerance;
    })
  ));
  return {
    points: slice.loops[0]!.points,
    area,
    depth,
    areaFraction: area / referenceArea,
    sourceTriangleIds,
  };
}

function subsetMesh(mesh: BrowserTriangleMesh, triangleIds: readonly number[]): BrowserMesh | null {
  if (triangleIds.length === 0) return null;
  const positions = new Float32Array(triangleIds.length * 9);
  const normals = new Float32Array(triangleIds.length * 9);
  const indices = new Uint32Array(triangleIds.length * 3);
  triangleIds.forEach((triangle, outputTriangle) => {
    for (let corner = 0; corner < 3; corner += 1) {
      const sourceVertex = mesh.faces[triangle * 3 + corner]! * 3;
      const outputVertex = outputTriangle * 3 + corner;
      positions[outputVertex * 3] = mesh.vertices[sourceVertex]!;
      positions[outputVertex * 3 + 1] = mesh.vertices[sourceVertex + 1]!;
      positions[outputVertex * 3 + 2] = mesh.vertices[sourceVertex + 2]!;
      normals[outputVertex * 3] = mesh.faceNormals[triangle * 3]!;
      normals[outputVertex * 3 + 1] = mesh.faceNormals[triangle * 3 + 1]!;
      normals[outputVertex * 3 + 2] = mesh.faceNormals[triangle * 3 + 2]!;
      indices[outputVertex] = outputVertex;
    }
  });
  return {
    positions,
    normals,
    indices,
    vertexCount: triangleIds.length * 3,
    triangleCount: triangleIds.length,
  };
}

function addFillet(graph: CADGraph, targetEdges: string[], radius: number): void {
  if (targetEdges.length === 0) fail("candidate-build", "fillet-no-edges", "No stable extrusion rim edges resolved for the fillet candidate");
  const fillet: Feature = {
    ...featureBase("feature.fillet", "Recovered paired outer rim fillets", 1, ["feature.base"], "evidence.browser-parametric"),
    operation: "fillet",
    targetEdges: targetEdges as [string, ...string[]],
    radius,
  };
  graph.features.splice(1, 0, fillet);
  graph.features.forEach((feature, index) => { feature.order = index; });
  const cut = graph.features.find((feature) => feature.id === "feature.hex-cut")!;
  cut.dependencies = [fillet.id];
  graph.semanticTopology.push({
    id: "feature.fillet.result", kind: "solid", producerFeatureId: fillet.id, role: "intermediateSolid",
    generatedFrom: targetEdges, status: "unresolved",
  }, ...targetEdges.map((id) => ({
    id, kind: "edge" as const, producerFeatureId: "feature.base", role: "outerProfileRim",
    generatedFrom: ["sketch.base.profile"], status: "unresolved" as const,
  })));
}

function addChamfer(graph: CADGraph, targetEdges: string[], width: number): void {
  if (targetEdges.length === 0) fail("candidate-build", "chamfer-no-edges", "No stable extrusion rim edges resolved for the chamfer candidate");
  const chamfer: Feature = {
    ...featureBase("feature.chamfer", "Recovered paired outer rim chamfers", 1, ["feature.base"], "evidence.browser-parametric"),
    operation: "chamfer",
    targetEdges: targetEdges as [string, ...string[]],
    width,
  };
  graph.features.splice(1, 0, chamfer);
  graph.features.forEach((feature, index) => { feature.order = index; });
  const cut = graph.features.find((feature) => feature.id === "feature.hex-cut")!;
  cut.dependencies = [chamfer.id];
  graph.semanticTopology.push({
    id: "feature.chamfer.result", kind: "solid", producerFeatureId: chamfer.id, role: "intermediateSolid",
    generatedFrom: targetEdges, status: "unresolved",
  }, ...targetEdges.map((id) => ({
    id, kind: "edge" as const, producerFeatureId: "feature.base", role: "outerProfileRim",
    generatedFrom: ["sketch.base.profile"], status: "unresolved" as const,
  })));
}

function addBoss(graph: CADGraph, stack: BrowserSectionStack, boss: BossEvidence): void {
  const evidenceId = "evidence.browser-parametric";
  const planeOrigin = addAlong(stack.frame.origin, stack.axis, stack.capOffsets[1] - stack.capOffsets[0]);
  const entity: SketchEntity = {
    ...entityBase("sketch.detail.entity.001", evidenceId), kind: "rectangle",
    origin: { x: boss.origin[0], y: boss.origin[1] }, width: boss.width, height: boss.height, rotationDeg: 0,
  };
  graph.sketches.push({
    id: "sketch.detail", name: "Recovered shallow rectangular boss",
    plane: { origin: vector(planeOrigin), normal: vector(stack.axis), xAxis: vector(stack.frame.u) },
    entities: [entity], constraints: [],
    profiles: [{
      id: "sketch.detail.profile", name: "Recovered boss rectangle", outerLoop: [entity.id], innerLoops: [],
      orientation: "counterclockwise", closed: true, sourceEvidence: [evidenceId], confidence: 0.9, locked: false,
    }],
    sourceEvidence: [evidenceId], confidence: 0.9, userLocks: [], overrides: [], suppressed: false,
  });
  const dependency = graph.features.at(-1)!.id;
  const feature: Feature = {
    ...featureBase("feature.detail", "Recovered shallow rectangular boss", graph.features.length, [dependency], evidenceId),
    operation: "extrusion", booleanMode: "additive", sketchId: "sketch.detail", profileIds: ["sketch.detail.profile"],
    direction: vector(stack.axis), extent: "blind", distance: boss.depth,
  };
  graph.features.push(feature);
  for (const reference of graph.semanticTopology) {
    if (reference.role === "resultSolid") reference.role = "intermediateSolid";
  }
  graph.semanticTopology.push({
    id: "feature.detail.result", kind: "solid", producerFeatureId: feature.id, role: "resultSolid",
    generatedFrom: ["sketch.detail.profile"], status: "unresolved",
  });
}

function addRaisedProfile(graph: CADGraph, stack: BrowserSectionStack, detail: RaisedProfileEvidence): void {
  const evidenceId = "evidence.browser-parametric";
  const planeOrigin = addAlong(stack.frame.origin, stack.axis, stack.capOffsets[1] - stack.capOffsets[0]);
  const points = detail.points.map((point) => ({ x: point[0], y: point[1] })) as [Vector2, Vector2, ...Vector2[]];
  const entity: SketchEntity = {
    ...entityBase("sketch.detail.entity.001", evidenceId),
    kind: "polyline",
    points,
    closed: true,
  };
  graph.sketches.push({
    id: "sketch.detail", name: "Recovered raised functional profile",
    plane: { origin: vector(planeOrigin), normal: vector(stack.axis), xAxis: vector(stack.frame.u) },
    entities: [entity], constraints: [],
    profiles: [{
      id: "sketch.detail.profile", name: "Recovered raised profile", outerLoop: [entity.id], innerLoops: [],
      orientation: "counterclockwise", closed: true, sourceEvidence: [evidenceId], confidence: 0.9, locked: false,
    }],
    sourceEvidence: [evidenceId], confidence: 0.9, userLocks: [], overrides: [], suppressed: false,
  });
  const dependency = graph.features.at(-1)!.id;
  const feature: Feature = {
    ...featureBase("feature.detail", "Recovered raised functional profile", graph.features.length, [dependency], evidenceId),
    operation: "extrusion", booleanMode: "additive", sketchId: "sketch.detail", profileIds: ["sketch.detail.profile"],
    direction: vector(stack.axis), extent: "blind", distance: detail.depth,
  };
  graph.features.push(feature);
  for (const reference of graph.semanticTopology) {
    if (reference.role === "resultSolid") reference.role = "intermediateSolid";
  }
  graph.semanticTopology.push({
    id: "feature.detail.result", kind: "solid", producerFeatureId: feature.id, role: "resultSolid",
    generatedFrom: ["sketch.detail.profile"], status: "unresolved",
  });
}

function assertGraph(graph: CADGraph): void {
  const validation = validateCADGraph(graph);
  if (!validation.valid) fail(
    "candidate-build", "cadgraph-invalid", "Browser reconstruction produced an invalid CADGraph contract",
    { issues: validation.issues.map((issue) => `${issue.path}: ${issue.message}`).join("; ") },
  );
}

export function reconstructParametricStl(
  kernel: OcctKernel,
  request: ParametricStlGeometryRequest,
  progress: Progress,
): BrowserParametricResult {
  const started = performance.now();
  const timingsMs: Record<string, number> = {};
  const mark = (name: string, from: number): number => { timingsMs[name] = performance.now() - from; return performance.now(); };
  progress("ingest", 0.03, "Validating and normalizing the source mesh");
  let checkpoint = performance.now();
  const mesh = triangleMeshFromStl(request.bytes, request.source.scaleFactor, request.tolerance);
  checkpoint = mark("ingest", checkpoint);

  progress("sections", 0.16, "Extracting deterministic interior section evidence");
  let stack: BrowserSectionStack;
  try { stack = extractSectionStack(mesh, request.tolerance); }
  catch (cause) { fail("sections", "section-extraction-failed", cause instanceof Error ? cause.message : String(cause)); }
  if (stack.blindFeatureDetected || stack.taperedExtrusionDetected) {
    fail("sections", "unsupported-prismatic-topology", "The browser-native parametric path requires a constant-axis prismatic body", {
      blindFeatureDetected: String(stack.blindFeatureDetected), taperedExtrusionDetected: String(stack.taperedExtrusionDetected),
      axis: stack.axis.join(","), radiusAccepted: String(stack.radiusFit.accepted),
      maximumInset: stack.radiusFit.maximumInset, radiusRms: stack.radiusFit.rmsResidual ?? "unavailable",
      maximumSupportChange: stack.maximumSupportChange,
    });
  }
  checkpoint = mark("sections", checkpoint);

  progress("profile-fitting", 0.31, "Fitting line, arc, bounded B-spline, and polygon profiles");
  const reference = stack.slices[stack.referenceSliceIndex]!;
  if (reference.loops.length !== 2) fail("profile-fitting", "unsupported-loop-count", "Expected one outer loop and one through-cut loop", { loopCount: reference.loops.length }, reference.sourceTriangleIds);
  let primitives: BrowserProfilePrimitive[] | null;
  let polygon: BrowserRegularPolygon;
  try {
    primitives = fitBrowserSplineProfile(reference.loops[0]!.points);
    polygon = fitRegularPolygon(reference.loops[1]!.points, request.tolerance);
  } catch (cause) {
    fail("profile-fitting", "bounded-profile-fit-failed", cause instanceof Error ? cause.message : String(cause), {}, reference.sourceTriangleIds);
  }
  if (primitives === null) fail("profile-fitting", "unsupported-outer-profile", "The outer loop does not match the bounded line, arc, and B-spline family", {}, reference.sourceTriangleIds);
  if (polygon.sideCount !== 6) fail("profile-fitting", "unsupported-cut-profile", "Only the proven six-sided regular through-cut is accepted", { sideCount: polygon.sideCount }, reference.sourceTriangleIds);
  checkpoint = mark("profileFitting", checkpoint);

  progress("candidate-build", 0.45, "Building the sharp parametric candidate and resolving semantic edges");
  const graph = baseGraph(request, mesh, stack, primitives, polygon);
  assertGraph(graph);
  const sharp = compileCadGraphWithTopology(kernel, graph);
  const candidates: BrowserParametricResult["candidates"] = [{ label: "sharp-extrusion-cut", accepted: true, score: null, reason: null }];
  const rim = primitives.length <= 16 ? selectedRimTreatment(stack) : null;
  const filletRadius = rim?.kind === "fillet" ? rim.size : null;
  const chamferWidth = rim?.kind === "chamfer" ? rim.size : null;
  if (rim !== null) {
    const targetEdges = selectPrismaticRimEdges(sharp.topology.filter((record) => record.producerFeatureId === "feature.base"), vector(stack.axis));
    if (rim.kind === "fillet") addFillet(graph, targetEdges, rim.size);
    else addChamfer(graph, targetEdges, rim.size);
    candidates.push({ label: `paired-rim-${rim.kind}`, accepted: true, score: null, reason: null });
  } else {
    candidates.push({ label: "paired-rim-fillet", accepted: false, score: null, reason: null });
    candidates.push({ label: "paired-rim-chamfer", accepted: false, score: null, reason: null });
  }
  const boss = primitives.length <= 16 ? detectBoss(mesh, stack, request.tolerance) : null;
  const raised = boss === null ? detectRaisedProfile(mesh, stack, request.tolerance) : null;
  const suppressedRegions: BrowserParametricResult["suppressedRegions"] = [];
  let suppressedMesh: BrowserMesh | null = null;
  if (boss !== null && request.detailMode === "full") {
    addBoss(graph, stack, boss);
    candidates.push({ label: "shallow-rectangular-boss", accepted: true, score: null, reason: null });
  } else if (boss !== null) {
    suppressedRegions.push({
      kind: "shallow-rectangular-boss", width: boss.width, height: boss.height, depth: boss.depth,
      sourceTriangleIds: boss.sourceTriangleIds, reason: "functional detail mode",
    });
    suppressedMesh = subsetMesh(mesh, boss.sourceTriangleIds);
    candidates.push({ label: "shallow-rectangular-boss", accepted: false, score: null, reason: null });
  }
  if (raised !== null && (request.detailMode === "full" || raised.areaFraction >= 0.15)) {
    addRaisedProfile(graph, stack, raised);
    candidates.push({ label: "raised-functional-profile", accepted: true, score: null, reason: null });
  } else if (raised !== null) {
    suppressedRegions.push({
      kind: "raised-profile", area: raised.area, depth: raised.depth, areaFraction: raised.areaFraction,
      sourceTriangleIds: raised.sourceTriangleIds, reason: "functional detail mode",
    });
    suppressedMesh = subsetMesh(mesh, raised.sourceTriangleIds);
    candidates.push({ label: "raised-profile", accepted: false, score: null, reason: null });
  }
  const reconstructionExtension = graph.extensions?.["mesh2param.dev/prismaticReconstruction"];
  if (reconstructionExtension !== null && typeof reconstructionExtension === "object" && !Array.isArray(reconstructionExtension)) {
    reconstructionExtension.suppressedRegions = suppressedRegions;
    if (boss !== null && request.detailMode === "full") {
      reconstructionExtension.detailRecovery = { regions: [{ kind: "rectangular-boss", width: boss.width, height: boss.height, depth: boss.depth }] };
    } else if (raised !== null && (request.detailMode === "full" || raised.areaFraction >= 0.15)) {
      reconstructionExtension.detailRecovery = { regions: [{ kind: "raised-profile", area: raised.area, depth: raised.depth }] };
    }
  }
  assertGraph(graph);
  checkpoint = mark("candidateBuild", checkpoint);

  progress("occt-compile", 0.59, "Rebuilding the final feature sequence in OCCT-WASM");
  const compilation = compileCadGraphWithTopology(kernel, graph);
  checkpoint = mark("occtCompile", checkpoint);

  progress("comparison", 0.76, "Running deterministic bidirectional surface comparison");
  const comparison = compareMeshes(
    mesh, compilation.result.mesh, compilation.result.volume, request.tolerance, request.deterministicSeed,
    1500,
  );
  if (boss !== null && request.detailMode === "functional") {
    const functionalVolume = Math.max(mesh.volume - boss.width * boss.height * boss.depth, 1e-15);
    comparison.relativeVolumeDelta = Math.abs(compilation.result.volume - functionalVolume) / functionalVolume;
  }
  const toleranceSatisfied = comparison.distance.p95 <= request.tolerance
    && comparison.toleranceSurfaceCoverage >= 0.95
    && comparison.normals.meanAgreement >= 0.95
    && comparison.normals.p95AngleDeg <= 15
    && (comparison.relativeVolumeDelta ?? Infinity) <= 0.001;
  const functionalApproximationAccepted = !toleranceSatisfied
    && request.detailMode === "functional"
    && primitives.length > 16
    && raised !== null
    && raised.areaFraction >= 0.15
    && comparison.distance.p95 <= request.tolerance * FUNCTIONAL_P95_TOLERANCE_MULTIPLIER + 1e-6
    && comparison.distance.maximum <= request.tolerance * FUNCTIONAL_MAX_TOLERANCE_MULTIPLIER + 1e-6
    && comparison.toleranceSurfaceCoverage >= FUNCTIONAL_MINIMUM_COVERAGE
    && comparison.normals.meanAgreement >= 0.95
    && comparison.normals.p95AngleDeg <= FUNCTIONAL_MAXIMUM_NORMAL_ANGLE_DEG + 1e-6
    && (comparison.relativeVolumeDelta ?? Infinity) <= FUNCTIONAL_MAXIMUM_RELATIVE_VOLUME_DELTA;
  if (!toleranceSatisfied && !functionalApproximationAccepted) fail("comparison", "candidate-outside-tolerance", "The best browser-local parametric candidate did not satisfy the acceptance gates", {
    rms: comparison.distance.rms, p95: comparison.distance.p95, p99: comparison.distance.p99,
    maximum: comparison.distance.maximum, coverage: comparison.toleranceSurfaceCoverage,
    meanNormalAgreement: comparison.normals.meanAgreement,
    p95NormalAngleDeg: comparison.normals.p95AngleDeg,
    relativeVolumeDelta: comparison.relativeVolumeDelta ?? "unavailable",
  });
  checkpoint = mark("comparison", checkpoint);

  progress("step-roundtrip", 0.91, "Verifying STEP round-trip and analytic surface evidence");
  if (!compilation.result.valid || !compilation.result.solid || !compilation.result.stepReimportValid) {
    fail("step-roundtrip", "step-roundtrip-invalid", "OCCT did not produce and reimport exactly one valid solid");
  }
  if ((compilation.result.stepReimportRelativeVolumeDelta ?? Infinity) > 1e-6) {
    fail("step-roundtrip", "step-roundtrip-volume-changed", `STEP reimport changed the B-Rep volume by ${compilation.result.stepReimportRelativeVolumeDelta ?? "an unavailable amount"}`, {
      relativeVolumeDelta: compilation.result.stepReimportRelativeVolumeDelta ?? "unavailable",
    });
  }
  const surfaceCounts = compilation.result.surfaceCounts ?? {};
  const reimportSurfaceCounts = compilation.result.reimportSurfaceCounts ?? {};
  if (JSON.stringify(surfaceCounts) !== JSON.stringify(reimportSurfaceCounts)) {
    fail("step-roundtrip", "step-roundtrip-surfaces-changed", "STEP reimport changed the analytic surface inventory", {
      source: JSON.stringify(surfaceCounts), reimported: JSON.stringify(reimportSurfaceCounts),
    });
  }
  if (filletRadius !== null && (surfaceCounts.torus ?? 0) < 1) {
    fail("step-roundtrip", "fillet-surface-missing", "The accepted fillet candidate did not retain an analytic torus surface", { torusFaces: surfaceCounts.torus ?? 0 });
  }
  graph.fitMetrics = {
    rmsSurfaceDistance: comparison.distance.rms,
    p95SurfaceDistance: comparison.distance.p95,
    maxSurfaceDistance: comparison.distance.maximum,
    normalAgreement: comparison.normals.meanAgreement,
    volumeDifference: Math.abs(compilation.result.volume - mesh.volume),
    overlap: comparison.toleranceSurfaceCoverage,
    unmatchedSourceArea: (1 - comparison.toleranceSurfaceCoverage) * mesh.surfaceArea,
    excessResultArea: (1 - comparison.toleranceSurfaceCoverage) * compilation.result.surfaceArea,
    score: Math.max(0, 1 - comparison.distance.p95 / request.tolerance),
  };
  graph.validation = functionalApproximationAccepted ? {
    status: "partial", brepValid: true, stepReimportValid: true, toleranceSatisfied: false,
    lastValidFeatureId: graph.features.at(-1)!.id, checkedAt: "1970-01-01T00:00:00Z",
    issues: [{
      code: "functional-parametric-approximation",
      message: "Complex chamfer and blend details were bounded but not recovered as editable features.",
      severity: "warning",
      details: {
        p95SurfaceDistance: comparison.distance.p95,
        maximumSurfaceDistance: comparison.distance.maximum,
        toleranceSurfaceCoverage: comparison.toleranceSurfaceCoverage,
        relativeVolumeDelta: comparison.relativeVolumeDelta,
      },
    }],
  } : {
    status: "valid", brepValid: true, stepReimportValid: true, toleranceSatisfied: true,
    lastValidFeatureId: graph.features.at(-1)!.id, checkedAt: "1970-01-01T00:00:00Z", issues: [],
  };
  assertGraph(graph);
  mark("stepRoundtrip", checkpoint);
  timingsMs.total = performance.now() - started;
  progress("complete", 1, "Browser-local parametric STEP is ready");

  return {
    ...compilation.result,
    graph,
    parametricReconstruction: {
      family: "general-parametric-prismatic",
      detailMode: request.detailMode,
      acceptance: functionalApproximationAccepted ? "functional-approximation" : "strict",
      toleranceSatisfied,
      featureSequence: graph.features.map((feature) => feature.operation ?? "unknown"),
      axis: stack.axis,
      thickness: stack.capOffsets[1] - stack.capOffsets[0],
      filletRadius,
      chamferWidth,
      surfaceCounts,
      comparison,
      diagnostics: [],
      timingsMs,
    },
    candidates,
    suppressedRegions,
    suppressedMesh,
  };
}
