import type {
  CADGraph,
  Feature,
  Plane3,
  Sketch,
  Vector3,
} from "./types.generated.js";
import { validateCADGraphSchema } from "./validator.generated.js";

export interface ContractIssue {
  path: string;
  code: string;
  message: string;
}

export interface ContractValidationResult {
  valid: boolean;
  issues: ContractIssue[];
}

export class CADGraphValidationError extends TypeError {
  readonly issues: ContractIssue[];

  constructor(issues: ContractIssue[]) {
    super(
      `Invalid CADGraph:\n${issues
        .map((issue) => `- ${issue.path || "/"}: ${issue.message}`)
        .join("\n")}`,
    );
    this.name = "CADGraphValidationError";
    this.issues = issues;
  }
}

function norm(vector: Vector3): number {
  return Math.hypot(vector.x, vector.y, vector.z);
}

function dot(left: Vector3, right: Vector3): number {
  return left.x * right.x + left.y * right.y + left.z * right.z;
}

function validateUnitVector(
  vector: Vector3,
  path: string,
  issues: ContractIssue[],
): void {
  if (Math.abs(norm(vector) - 1) > 1e-6) {
    issues.push({ path, code: "unit-vector", message: "must be a unit vector" });
  }
}

function validatePlane(plane: Plane3, path: string, issues: ContractIssue[]): void {
  validateUnitVector(plane.normal, `${path}/normal`, issues);
  validateUnitVector(plane.xAxis, `${path}/xAxis`, issues);
  if (Math.abs(dot(plane.normal, plane.xAxis)) > 1e-6) {
    issues.push({
      path,
      code: "orthogonal-basis",
      message: "normal and xAxis must be perpendicular",
    });
  }
}

function uniqueIdSet(
  values: ReadonlyArray<{ id: string }>,
  path: string,
  issues: ContractIssue[],
): Set<string> {
  const result = new Set<string>();
  for (const value of values) {
    if (result.has(value.id)) {
      issues.push({
        path,
        code: "duplicate-id",
        message: `duplicate ID ${value.id}`,
      });
    }
    result.add(value.id);
  }
  return result;
}

function requireReferences(
  values: readonly string[],
  allowed: ReadonlySet<string>,
  path: string,
  issues: ContractIssue[],
): void {
  for (const value of values) {
    if (!allowed.has(value)) {
      issues.push({
        path,
        code: "unknown-reference",
        message: `unknown reference ${value}`,
      });
    }
  }
}

function validateSketch(
  sketch: Sketch,
  path: string,
  evidenceIds: ReadonlySet<string>,
  issues: ContractIssue[],
): void {
  validatePlane(sketch.plane, `${path}/plane`, issues);
  const entityIds = uniqueIdSet(sketch.entities, `${path}/entities`, issues);
  uniqueIdSet(sketch.constraints, `${path}/constraints`, issues);
  uniqueIdSet(sketch.profiles, `${path}/profiles`, issues);
  requireReferences(sketch.sourceEvidence, evidenceIds, `${path}/sourceEvidence`, issues);

  sketch.entities.forEach((entity, index) => {
    const entityPath = `${path}/entities/${index}`;
    requireReferences(entity.sourceEvidence, evidenceIds, `${entityPath}/sourceEvidence`, issues);
    if ((entity.kind === "line" || entity.kind === "constructionLine") &&
        entity.start.x === entity.end.x && entity.start.y === entity.end.y) {
      issues.push({ path: entityPath, code: "zero-length", message: "line endpoints must differ" });
    }
    if (entity.kind === "constructionAxis" && Math.hypot(entity.direction.x, entity.direction.y) <= 1e-12) {
      issues.push({ path: `${entityPath}/direction`, code: "zero-vector", message: "must be non-zero" });
    }
    if (entity.kind === "circularArc" && Math.abs(entity.startAngleDeg - entity.endAngleDeg) <= 1e-12) {
      issues.push({ path: entityPath, code: "zero-sweep", message: "arc sweep must be non-zero" });
    }
    if (entity.kind === "closedProfile") {
      requireReferences(
        [...entity.outerLoop, ...entity.innerLoops.flat()],
        new Set([...entityIds].filter((id) => id !== entity.id)),
        entityPath,
        issues,
      );
    }
  });

  sketch.constraints.forEach((constraint, index) => {
    const constraintPath = `${path}/constraints/${index}`;
    requireReferences(constraint.entityIds, entityIds, `${constraintPath}/entityIds`, issues);
    requireReferences(constraint.sourceEvidence, evidenceIds, `${constraintPath}/sourceEvidence`, issues);
    const dimensional = new Set([
      "distance",
      "horizontalDistance",
      "verticalDistance",
      "angle",
      "radius",
      "diameter",
    ]);
    if (dimensional.has(constraint.kind) && constraint.value == null) {
      issues.push({ path: constraintPath, code: "missing-value", message: `${constraint.kind} requires value` });
    }
    if ((constraint.kind === "radius" || constraint.kind === "diameter") &&
        constraint.value != null && constraint.value <= 0) {
      issues.push({ path: `${constraintPath}/value`, code: "positive-value", message: "must be positive" });
    }
  });

  sketch.profiles.forEach((profile, index) => {
    const profilePath = `${path}/profiles/${index}`;
    requireReferences(profile.outerLoop, entityIds, `${profilePath}/outerLoop`, issues);
    profile.innerLoops.forEach((loop, loopIndex) => {
      requireReferences(loop, entityIds, `${profilePath}/innerLoops/${loopIndex}`, issues);
    });
    requireReferences(profile.sourceEvidence, evidenceIds, `${profilePath}/sourceEvidence`, issues);
  });
}

function validateFeatureParameters(feature: Feature, path: string, issues: ContractIssue[]): void {
  switch (feature.operation) {
    case "extrusion":
      if (norm(feature.direction) <= 1e-12) {
        issues.push({ path: `${path}/direction`, code: "zero-vector", message: "must be non-zero" });
      }
      if ((feature.extent === "blind" || feature.extent === "symmetric") && feature.distance == null) {
        issues.push({ path, code: "missing-distance", message: `${feature.extent} extrusion requires distance` });
      }
      if (feature.extent === "toFace" && feature.targetFace == null) {
        issues.push({ path, code: "missing-target", message: "toFace extrusion requires targetFace" });
      }
      break;
    case "pocket":
      if (norm(feature.direction) <= 1e-12) {
        issues.push({ path: `${path}/direction`, code: "zero-vector", message: "must be non-zero" });
      }
      if (feature.extent === "toFace" && feature.targetFace == null) {
        issues.push({ path, code: "missing-target", message: "toFace pocket requires targetFace" });
      }
      break;
    case "hole":
      if (norm(feature.axis) <= 1e-12) {
        issues.push({ path: `${path}/axis`, code: "zero-vector", message: "must be non-zero" });
      }
      if (feature.holeType === "blind" && feature.depth == null) {
        issues.push({ path, code: "missing-depth", message: "blind hole requires depth" });
      }
      break;
    case "counterbore":
      if (norm(feature.axis) <= 1e-12) {
        issues.push({ path: `${path}/axis`, code: "zero-vector", message: "must be non-zero" });
      }
      if (feature.holeType === "blind" && feature.depth == null) {
        issues.push({ path, code: "missing-depth", message: "blind counterbore requires depth" });
      }
      if (feature.boreDiameter <= feature.diameter) {
        issues.push({ path: `${path}/boreDiameter`, code: "diameter-order", message: "must exceed diameter" });
      }
      if (feature.depth != null && feature.boreDepth >= feature.depth) {
        issues.push({ path: `${path}/boreDepth`, code: "depth-order", message: "must be less than depth" });
      }
      break;
    case "countersink":
      if (norm(feature.axis) <= 1e-12) {
        issues.push({ path: `${path}/axis`, code: "zero-vector", message: "must be non-zero" });
      }
      if (feature.holeType === "blind" && feature.depth == null) {
        issues.push({ path, code: "missing-depth", message: "blind countersink requires depth" });
      }
      if (feature.sinkDiameter <= feature.diameter) {
        issues.push({ path: `${path}/sinkDiameter`, code: "diameter-order", message: "must exceed diameter" });
      }
      break;
    case "linearPattern":
      if (norm(feature.direction) <= 1e-12) {
        issues.push({ path: `${path}/direction`, code: "zero-vector", message: "must be non-zero" });
      }
      break;
    case "mirror":
      validatePlane(feature.plane, `${path}/plane`, issues);
      break;
    case "revolution":
    case "circularPattern":
      if (norm(feature.axis.direction) <= 1e-12) {
        issues.push({ path: `${path}/axis/direction`, code: "zero-vector", message: "must be non-zero" });
      }
      break;
    case "chamfer":
    case "fillet":
    case "importedFaceted":
    case "reconstructedSurfaceNetwork":
      break;
  }
}

function graphInvariantIssues(graph: CADGraph): ContractIssue[] {
  const issues: ContractIssue[] = [];
  const sketchIds = uniqueIdSet(graph.sketches, "/sketches", issues);
  const featureIds = uniqueIdSet(graph.features, "/features", issues);
  const topologyIds = uniqueIdSet(graph.semanticTopology, "/semanticTopology", issues);
  const evidenceIds = uniqueIdSet(graph.sourceEvidence, "/sourceEvidence", issues);
  const profileIds = new Set(graph.sketches.flatMap((sketch) => sketch.profiles.map((profile) => profile.id)));

  const frame = graph.sourceCoordinateFrame;
  const axes: Array<[string, Vector3]> = [["xAxis", frame.xAxis], ["yAxis", frame.yAxis], ["zAxis", frame.zAxis]];
  axes.forEach(([name, axis]) => validateUnitVector(axis, `/sourceCoordinateFrame/${name}`, issues));
  for (let left = 0; left < axes.length; left += 1) {
    for (let right = left + 1; right < axes.length; right += 1) {
      const leftAxis = axes[left];
      const rightAxis = axes[right];
      if (leftAxis && rightAxis && Math.abs(dot(leftAxis[1], rightAxis[1])) > 1e-6) {
        issues.push({
          path: "/sourceCoordinateFrame",
          code: "orthogonal-basis",
          message: `${leftAxis[0]} and ${rightAxis[0]} must be perpendicular`,
        });
      }
    }
  }
  requireReferences(frame.evidenceIds, evidenceIds, "/sourceCoordinateFrame/evidenceIds", issues);

  graph.sketches.forEach((sketch, index) => {
    validateSketch(sketch, `/sketches/${index}`, evidenceIds, issues);
  });

  const orderById = new Map(graph.features.map((feature) => [feature.id, feature.order]));
  let previousOrder = -1;
  const seenOrders = new Set<number>();
  graph.features.forEach((feature, index) => {
    const path = `/features/${index}`;
    if (feature.order < previousOrder) {
      issues.push({ path: `${path}/order`, code: "feature-order", message: "features must be in ascending order" });
    }
    previousOrder = feature.order;
    if (seenOrders.has(feature.order)) {
      issues.push({ path: `${path}/order`, code: "duplicate-order", message: `duplicate order ${feature.order}` });
    }
    seenOrders.add(feature.order);
    requireReferences(feature.dependencies, featureIds, `${path}/dependencies`, issues);
    requireReferences(feature.sourceEvidence, evidenceIds, `${path}/sourceEvidence`, issues);
    requireReferences(feature.semanticOutputs, topologyIds, `${path}/semanticOutputs`, issues);
    for (const dependency of feature.dependencies) {
      const dependencyOrder = orderById.get(dependency);
      if (dependencyOrder !== undefined && dependencyOrder >= feature.order) {
        issues.push({ path: `${path}/dependencies`, code: "forward-dependency", message: `${dependency} must have an earlier order` });
      }
    }
    if (feature.operation === "extrusion" || feature.operation === "pocket" || feature.operation === "revolution") {
      requireReferences([feature.sketchId], sketchIds, `${path}/sketchId`, issues);
      requireReferences(feature.profileIds, profileIds, `${path}/profileIds`, issues);
    }
    if (feature.operation === "linearPattern" || feature.operation === "circularPattern" || feature.operation === "mirror") {
      requireReferences(feature.sourceFeatureIds, new Set(feature.dependencies), `${path}/sourceFeatureIds`, issues);
    }
    validateFeatureParameters(feature, path, issues);
  });

  graph.semanticTopology.forEach((reference, index) => {
    requireReferences([reference.producerFeatureId], featureIds, `/semanticTopology/${index}/producerFeatureId`, issues);
  });
  if (graph.validation.lastValidFeatureId != null) {
    requireReferences([graph.validation.lastValidFeatureId], featureIds, "/validation/lastValidFeatureId", issues);
  }
  if (graph.validation.status === "valid" &&
      !(graph.validation.brepValid === true &&
        graph.validation.stepReimportValid === true &&
        graph.validation.toleranceSatisfied === true)) {
    issues.push({
      path: "/validation",
      code: "invalid-validity-claim",
      message: "valid status requires B-Rep, STEP reimport and tolerance checks to pass",
    });
  }
  return issues;
}

export function validateCADGraph(value: unknown): ContractValidationResult {
  const schemaResult = validateCADGraphSchema(value);
  if (!schemaResult.valid) {
    return {
      valid: false,
      issues: schemaResult.errors.map((error) => ({
        path: error.instancePath || "/",
        code: error.keyword,
        message: error.message ?? "schema validation failed",
      })),
    };
  }
  const issues = graphInvariantIssues(value as CADGraph);
  return { valid: issues.length === 0, issues };
}

export function isCADGraph(value: unknown): value is CADGraph {
  return validateCADGraph(value).valid;
}

export function assertCADGraph(value: unknown): asserts value is CADGraph {
  const result = validateCADGraph(value);
  if (!result.valid) {
    throw new CADGraphValidationError(result.issues);
  }
}

export function parseCADGraph(value: unknown): CADGraph {
  assertCADGraph(value);
  return value;
}
