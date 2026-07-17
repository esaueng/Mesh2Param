import type {
  CADGraph,
  Feature,
  Plane3,
  Sketch,
  SketchEntity,
  SketchProfile,
  Vector2,
  Vector3,
} from "@mesh2param/contracts";
import { OcctKernel, type ShapeHandle, type Vec3 } from "occt-wasm";

import type { BrowserCadResult } from "./types";
import { reconstructLayeredCurvedShape } from "./layered";
import { analyzeStl } from "./stl";

interface ProducedFeature {
  tool: ShapeHandle;
  mode: "base" | "additive" | "subtractive";
}

function add(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

function scale(a: Vec3, value: number): Vec3 {
  return { x: a.x * value, y: a.y * value, z: a.z * value };
}

function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
}

function length(a: Vec3): number {
  return Math.hypot(a.x, a.y, a.z);
}

function unit(a: Vec3): Vec3 {
  const magnitude = length(a);
  if (magnitude < 1e-12) throw new Error("A CADGraph direction has zero length");
  return scale(a, 1 / magnitude);
}

function pointOnPlane(plane: Plane3, point: Vector2): Vec3 {
  const x = unit(plane.xAxis);
  const y = unit(cross(unit(plane.normal), x));
  return add(add(plane.origin, scale(x, point.x)), scale(y, point.y));
}

function circlePoint(plane: Plane3, center: Vector2, radius: number, angle: number): Vec3 {
  const x = unit(plane.xAxis);
  const y = unit(cross(unit(plane.normal), x));
  return add(pointOnPlane(plane, center), add(scale(x, Math.cos(angle) * radius), scale(y, Math.sin(angle) * radius)));
}

function entityEdges(kernel: OcctKernel, sketch: Sketch, entity: SketchEntity): ShapeHandle[] {
  if (entity.suppressed || entity.construction) return [];
  switch (entity.kind) {
    case "line":
      return [kernel.makeLineEdge(pointOnPlane(sketch.plane, entity.start), pointOnPlane(sketch.plane, entity.end))];
    case "polyline": {
      const edges: ShapeHandle[] = [];
      for (let index = 1; index < entity.points.length; index += 1) {
        edges.push(kernel.makeLineEdge(pointOnPlane(sketch.plane, entity.points[index - 1]!), pointOnPlane(sketch.plane, entity.points[index]!)));
      }
      if (entity.closed) {
        edges.push(kernel.makeLineEdge(pointOnPlane(sketch.plane, entity.points.at(-1)!), pointOnPlane(sketch.plane, entity.points[0])));
      }
      return edges;
    }
    case "rectangle": {
      const angle = entity.rotationDeg * Math.PI / 180;
      const rotate = (x: number, y: number): Vector2 => ({
        x: entity.origin.x + x * Math.cos(angle) - y * Math.sin(angle),
        y: entity.origin.y + x * Math.sin(angle) + y * Math.cos(angle),
      });
      const points = [rotate(0, 0), rotate(entity.width, 0), rotate(entity.width, entity.height), rotate(0, entity.height)];
      return points.map((point, index) => kernel.makeLineEdge(
        pointOnPlane(sketch.plane, point),
        pointOnPlane(sketch.plane, points[(index + 1) % points.length]!),
      ));
    }
    case "circle":
      return [kernel.makeCircleEdge(pointOnPlane(sketch.plane, entity.center), unit(sketch.plane.normal), entity.radius)];
    case "circularArc": {
      const start = entity.startAngleDeg * Math.PI / 180;
      let end = entity.endAngleDeg * Math.PI / 180;
      if (entity.clockwise && end > start) end -= 2 * Math.PI;
      if (!entity.clockwise && end < start) end += 2 * Math.PI;
      const mid = (start + end) / 2;
      return [kernel.makeArcEdge(
        circlePoint(sketch.plane, entity.center, entity.radius, start),
        circlePoint(sketch.plane, entity.center, entity.radius, mid),
        circlePoint(sketch.plane, entity.center, entity.radius, end),
      )];
    }
    default:
      return [];
  }
}

function profileWire(kernel: OcctKernel, sketch: Sketch, entityIds: readonly string[]): ShapeHandle {
  const byId = new Map(sketch.entities.map((entity) => [entity.id, entity]));
  const edges = entityIds.flatMap((id) => {
    const entity = byId.get(id);
    if (entity === undefined) throw new Error(`Sketch entity ${id} was not found`);
    return entityEdges(kernel, sketch, entity);
  });
  if (edges.length === 0) throw new Error("A sketch profile did not contain any buildable edges");
  return kernel.makeWire(edges);
}

function profileFace(kernel: OcctKernel, sketch: Sketch, profile: SketchProfile): ShapeHandle {
  let face = kernel.makeFace(profileWire(kernel, sketch, profile.outerLoop));
  if (profile.innerLoops.length > 0) {
    face = kernel.addHolesInFace(face, profile.innerLoops.map((loop) => profileWire(kernel, sketch, loop)));
  }
  return face;
}

function sketchFaces(kernel: OcctKernel, graph: CADGraph, sketchId: string, profileIds: readonly string[]): ShapeHandle[] {
  const sketch = graph.sketches.find((candidate) => candidate.id === sketchId);
  if (sketch === undefined) throw new Error(`Sketch ${sketchId} was not found`);
  return profileIds.map((profileId) => {
    const profile = sketch.profiles.find((candidate) => candidate.id === profileId);
    if (profile === undefined) throw new Error(`Sketch profile ${profileId} was not found`);
    return profileFace(kernel, sketch, profile);
  });
}

function orientAlong(kernel: OcctKernel, shape: ShapeHandle, direction: Vector3): ShapeHandle {
  const target = unit(direction);
  const z = { x: 0, y: 0, z: 1 };
  const cosine = Math.max(-1, Math.min(1, dot(z, target)));
  if (cosine > 1 - 1e-12) return shape;
  const rotationAxis = cosine < -1 + 1e-12 ? { x: 1, y: 0, z: 0 } : unit(cross(z, target));
  return kernel.rotate(shape, { point: { x: 0, y: 0, z: 0 }, direction: rotationAxis }, Math.acos(cosine));
}

function cylinderTool(kernel: OcctKernel, position: Vector3, axis: Vector3, radius: number, depth: number, margin: number): ShapeHandle {
  const direction = unit(axis);
  const cylinder = orientAlong(kernel, kernel.makeCylinder(radius, depth + margin * 2), direction);
  const start = add(position, scale(direction, -margin));
  return kernel.translate(cylinder, start.x, start.y, start.z);
}

function applyBoolean(kernel: OcctKernel, current: ShapeHandle | null, produced: ProducedFeature): ShapeHandle {
  if (produced.mode === "base") return produced.tool;
  if (current === null) throw new Error(`A ${produced.mode} feature cannot run before a base feature`);
  return produced.mode === "additive" ? kernel.fuse(current, produced.tool) : kernel.cut(current, produced.tool);
}

function buildFeature(
  kernel: OcctKernel,
  graph: CADGraph,
  feature: Feature,
  current: ShapeHandle | null,
  produced: Map<string, ProducedFeature>,
): ProducedFeature {
  switch (feature.operation) {
    case "extrusion": {
      const distance = feature.distance ?? (() => { throw new Error(`${feature.extent} extrusion requires a distance`); })();
      const direction = unit(feature.direction);
      const tools = sketchFaces(kernel, graph, feature.sketchId, feature.profileIds).map((face) => {
        let tool = kernel.extrude(face, direction.x * distance, direction.y * distance, direction.z * distance);
        if (feature.extent === "symmetric") tool = kernel.translate(tool, -direction.x * distance / 2, -direction.y * distance / 2, -direction.z * distance / 2);
        return tool;
      });
      return { tool: tools.length === 1 ? tools[0]! : kernel.fuseAll(tools), mode: feature.booleanMode };
    }
    case "pocket": {
      const direction = unit(feature.direction);
      const tools = sketchFaces(kernel, graph, feature.sketchId, feature.profileIds)
        .map((face) => kernel.extrude(face, direction.x * feature.depth, direction.y * feature.depth, direction.z * feature.depth));
      return { tool: tools.length === 1 ? tools[0]! : kernel.fuseAll(tools), mode: "subtractive" };
    }
    case "hole":
    case "counterbore":
    case "countersink": {
      if (current === null) throw new Error("A hole requires an existing solid");
      const bbox = kernel.getBoundingBox(current, false);
      const span = Math.hypot(bbox.xmax - bbox.xmin, bbox.ymax - bbox.ymin, bbox.zmax - bbox.zmin);
      const margin = Math.max(graph.projectTolerance.linearResolution * 4, span * 0.02, 0.01);
      const depth = feature.holeType === "through" ? span + margin * 2 : (feature.depth ?? span);
      const tools = [cylinderTool(kernel, feature.position, feature.axis, feature.diameter / 2, depth, margin)];
      if (feature.operation === "counterbore") {
        tools.push(cylinderTool(kernel, feature.position, feature.axis, feature.boreDiameter / 2, feature.boreDepth, margin));
      } else if (feature.operation === "countersink") {
        const height = (feature.sinkDiameter - feature.diameter) / 2 / Math.tan(feature.sinkAngleDeg * Math.PI / 360);
        const cone = orientAlong(kernel, kernel.makeCone(feature.sinkDiameter / 2, feature.diameter / 2, height + margin), feature.axis);
        const start = add(feature.position, scale(unit(feature.axis), -margin));
        tools.push(kernel.translate(cone, start.x, start.y, start.z));
      }
      return { tool: tools.length === 1 ? tools[0]! : kernel.fuseAll(tools), mode: "subtractive" };
    }
    case "revolution": {
      const faces = sketchFaces(kernel, graph, feature.sketchId, feature.profileIds);
      const tools = faces.map((face) => kernel.revolve(
        face,
        { point: feature.axis.origin, direction: unit(feature.axis.direction) },
        feature.angleDeg * Math.PI / 180,
      ));
      return { tool: tools.length === 1 ? tools[0]! : kernel.fuseAll(tools), mode: feature.booleanMode };
    }
    case "linearPattern": {
      const direction = unit(feature.direction);
      const source = feature.sourceFeatureIds.map((id) => produced.get(id) ?? (() => { throw new Error(`Pattern source ${id} was not found`); })());
      const copies: ShapeHandle[] = [];
      for (const item of source) {
        for (let index = 1; index < feature.count; index += 1) {
          copies.push(kernel.translate(item.tool, direction.x * feature.spacing * index, direction.y * feature.spacing * index, direction.z * feature.spacing * index));
        }
      }
      return { tool: copies.length === 1 ? copies[0]! : kernel.fuseAll(copies), mode: source[0]!.mode };
    }
    case "circularPattern": {
      const source = feature.sourceFeatureIds.map((id) => produced.get(id) ?? (() => { throw new Error(`Pattern source ${id} was not found`); })());
      const copies: ShapeHandle[] = [];
      for (const item of source) {
        for (let index = 1; index < feature.count; index += 1) {
          copies.push(kernel.rotate(item.tool, { point: feature.axis.origin, direction: unit(feature.axis.direction) }, feature.totalAngleDeg * Math.PI / 180 * index / feature.count));
        }
      }
      return { tool: copies.length === 1 ? copies[0]! : kernel.fuseAll(copies), mode: source[0]!.mode };
    }
    case "mirror": {
      const source = feature.sourceFeatureIds.map((id) => produced.get(id) ?? (() => { throw new Error(`Mirror source ${id} was not found`); })());
      const copies = source.map((item) => kernel.mirror(item.tool, feature.plane.origin, unit(feature.plane.normal)));
      return { tool: copies.length === 1 ? copies[0]! : kernel.fuseAll(copies), mode: source[0]!.mode };
    }
    case "fillet":
    case "chamfer":
      throw new Error(`${feature.operation} needs resolved semantic edge references and is not available in browser-local mode yet`);
    case "importedFaceted":
      throw new Error("Imported faceted features must be reconstructed from the source mesh before browser-local rebuild");
    default:
      throw new Error(`Unsupported CAD operation: ${(feature as Feature).operation}`);
  }
}

export function compileCadGraph(kernel: OcctKernel, graph: CADGraph): BrowserCadResult {
  let current: ShapeHandle | null = null;
  const produced = new Map<string, ProducedFeature>();
  const features = [...graph.features].filter((feature) => !feature.suppressed).sort((a, b) => a.order - b.order);
  for (const feature of features) {
    const result = buildFeature(kernel, graph, feature, current, produced);
    produced.set(feature.id, result);
    current = applyBoolean(kernel, current, result);
  }
  if (current === null) throw new Error("The CADGraph has no active features");
  return shapeResult(kernel, current, features.length, graph.projectTolerance.surfaceDeviation, graph.projectTolerance.angularDeviationDeg * Math.PI / 180);
}

function shapeResult(
  kernel: OcctKernel,
  current: ShapeHandle,
  featureCount: number,
  linearDeflection: number,
  angularDeflection: number,
  validateStep = true,
  meshProxy?: BrowserCadResult,
): BrowserCadResult {
  const valid = kernel.isValid(current);
  const sourceSolidCount = countSolids(kernel, current);
  const solid = sourceSolidCount > 0;
  const step = validateStep ? kernel.exportStep(current) : "";
  const reimported = validateStep ? kernel.importStep(step) : null;
  const stepReimportValid = reimported !== null
    && kernel.isValid(reimported)
    && countSolids(kernel, reimported) === sourceSolidCount
    && sourceSolidCount > 0;
  const mesh = meshProxy?.mesh ?? kernel.tessellate(current, {
    linearDeflection,
    angularDeflection,
  });
  const bbox = meshProxy === undefined ? kernel.getBoundingBox(current, true) : null;
  return {
    step,
    mesh,
    valid,
    solid,
    stepReimportValid,
    // STL orientation can make OCCT report a signed mass property. Volume is
    // a physical magnitude throughout the project-file contract.
    volume: meshProxy?.volume ?? Math.abs(kernel.getVolume(current)),
    surfaceArea: meshProxy?.surfaceArea ?? kernel.getSurfaceArea(current),
    bounds: meshProxy?.bounds ?? [[bbox!.xmin, bbox!.ymin, bbox!.zmin], [bbox!.xmax, bbox!.ymax, bbox!.zmax]],
    featureCount,
    ...(meshProxy?.diagnostics === undefined ? {} : { diagnostics: meshProxy.diagnostics }),
  };
}

function countSolids(kernel: OcctKernel, shape: ShapeHandle): number {
  return kernel.isSolid(shape) ? 1 : kernel.getSubShapes(shape, "solid").length;
}

function solidifyStl(kernel: OcctKernel, shape: ShapeHandle, tolerance: number): ShapeHandle {
  const faces = kernel.getSubShapes(shape, "face");
  if (faces.length === 0) throw new Error("The STL did not contain any importable faces");

  const sewn = kernel.sewAndSolidify(faces, tolerance);
  if (countSolids(kernel, sewn) > 0) return sewn;

  // OCCT sews a disconnected watertight STL into a compound of closed shells, but its
  // bulk solidifier does not promote those shells individually. Solidify each component
  // so multi-body meshes export as a compound containing real solids instead of shells.
  const shells = kernel.getSubShapes(sewn, "shell");
  if (shells.length < 2) return sewn;
  const solids = shells.map((shell) => kernel.sewAndSolidify(
    kernel.getSubShapes(shell, "face"),
    tolerance,
  ));
  if (!solids.every((solid) => kernel.isSolid(solid) && kernel.isValid(solid))) return sewn;
  return kernel.makeCompound(solids);
}

export function compileStl(
  kernel: OcctKernel,
  bytes: ArrayBuffer,
  tolerance: number,
  solidify = true,
  validateStep = true,
): BrowserCadResult {
  const source = analyzeStl(bytes);
  let shape = kernel.importStl(stlText(bytes));
  if (solidify && !kernel.isSolid(shape)) {
    shape = solidifyStl(kernel, shape, tolerance);
  }
  return shapeResult(kernel, shape, 1, tolerance, 0.35, validateStep, source);
}

export function compileCurvedStl(
  kernel: OcctKernel,
  bytes: ArrayBuffer,
  tolerance: number,
  progress?: (stage: string) => void,
): BrowserCadResult {
  if (!Number.isFinite(tolerance) || tolerance <= 0) {
    throw new Error("Curved reconstruction tolerance must be a finite positive number");
  }
  const source = analyzeStl(bytes);
  if (!source.valid || !source.solid || source.diagnostics?.watertight !== true) {
    throw new Error("Curved reconstruction requires one valid, consistently wound watertight STL");
  }
  const reconstructed = reconstructLayeredCurvedShape(kernel, source.mesh.positions, tolerance, progress);
  const result = shapeResult(kernel, reconstructed.shape, 1, Math.max(tolerance * 0.5, 0.01), 0.15);
  const relativeVolumeDelta = Math.abs(result.volume - source.volume) / Math.max(source.volume, 1e-12);
  const maximumBoundsDelta = Math.max(
    ...result.bounds.flatMap((bound, boundIndex) => bound.map((value, axis) => Math.abs(value - source.bounds[boundIndex]![axis]!))),
  );
  const diagonal = Math.hypot(
    source.bounds[1][0] - source.bounds[0][0],
    source.bounds[1][1] - source.bounds[0][1],
    source.bounds[1][2] - source.bounds[0][2],
  );
  if (relativeVolumeDelta > 0.08) {
    throw new Error(
      `Curved reconstruction changed volume by ${(relativeVolumeDelta * 100).toFixed(2)}% (source ${source.volume.toFixed(4)}, result ${result.volume.toFixed(4)}); the 8% safety limit is enforced`,
    );
  }
  if (maximumBoundsDelta > Math.max(tolerance * 4, diagonal * 0.01)) {
    throw new Error(`Curved reconstruction moved a model bound by ${maximumBoundsDelta.toFixed(4)} project units`);
  }
  const faceSurfaces: Record<string, number> = {};
  for (const face of kernel.getSubShapes(reconstructed.shape, "face")) {
    const kind = kernel.surfaceType(face);
    faceSurfaces[kind] = (faceSurfaces[kind] ?? 0) + 1;
  }
  const curvedSurfaceCount = ["bspline", "bezier", "cylinder", "cone", "sphere", "torus", "revolution", "extrusion"]
    .reduce((count, kind) => count + (faceSurfaces[kind] ?? 0), 0);
  if (curvedSurfaceCount === 0) {
    throw new Error("Curved reconstruction did not produce a genuine analytic, swept, or spline surface");
  }
  result.curvedReconstruction = {
    scope: "axis-aligned layered approximate curved B-Rep",
    ...reconstructed.evidence,
    sourceVolume: source.volume,
    resultVolume: result.volume,
    relativeVolumeDelta,
    maximumBoundsDelta,
    faceSurfaces,
  };
  return result;
}

function stlText(bytes: ArrayBuffer): string {
  if (bytes.byteLength >= 84) {
    const view = new DataView(bytes);
    const triangleCount = view.getUint32(80, true);
    if (84 + triangleCount * 50 === bytes.byteLength) {
      const lines = ["solid mesh2param"];
      let offset = 84;
      for (let triangle = 0; triangle < triangleCount; triangle += 1, offset += 50) {
        lines.push(`facet normal ${view.getFloat32(offset, true)} ${view.getFloat32(offset + 4, true)} ${view.getFloat32(offset + 8, true)}`);
        lines.push("outer loop");
        for (let vertex = 0; vertex < 3; vertex += 1) {
          const base = offset + 12 + vertex * 12;
          lines.push(`vertex ${view.getFloat32(base, true)} ${view.getFloat32(base + 4, true)} ${view.getFloat32(base + 8, true)}`);
        }
        lines.push("endloop", "endfacet");
      }
      lines.push("endsolid mesh2param");
      return lines.join("\n");
    }
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}
