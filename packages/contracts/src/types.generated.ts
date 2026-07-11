/* eslint-disable */
/**
 * GENERATED from schema/cadgraph.schema.json.
 * Schema SHA-256: 7242278e2358fd7e36a93905dff96f03b8e36f49d1326852f646b319976af2e0
 * Run `pnpm generate` in this package after changing the schema.
 */

/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "identifier".
 */
export type Identifier = string;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "units".
 */
export type Units = "mm" | "cm" | "m" | "in" | "ft";
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "confidence".
 */
export type Confidence = number;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sketchEntity".
 */
export type SketchEntity =
  | PointEntity
  | ConstructionPointEntity
  | LineEntity
  | ConstructionLineEntity
  | PolylineEntity
  | RectangleEntity
  | CircleEntity
  | CircularArcEntity
  | ClosedProfileEntity
  | ConstructionAxisEntity;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "pointEntity".
 */
export type PointEntity = EntityBase & {
  kind?: "point";
  construction?: false;
  position: Vector2;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "constructionPointEntity".
 */
export type ConstructionPointEntity = EntityBase & {
  kind?: "constructionPoint";
  construction?: true;
  position: Vector2;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "lineEntity".
 */
export type LineEntity = EntityBase & {
  kind?: "line";
  construction?: false;
  start: Vector2;
  end: Vector2;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "constructionLineEntity".
 */
export type ConstructionLineEntity = EntityBase & {
  kind?: "constructionLine";
  construction?: true;
  start: Vector2;
  end: Vector2;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "polylineEntity".
 */
export type PolylineEntity = EntityBase & {
  kind?: "polyline";
  construction?: false;
  /**
   * @minItems 2
   */
  points: [Vector2, Vector2, ...Vector2[]];
  closed: boolean;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "rectangleEntity".
 */
export type RectangleEntity = EntityBase & {
  kind?: "rectangle";
  construction?: false;
  origin: Vector2;
  width: number;
  height: number;
  rotationDeg: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "circleEntity".
 */
export type CircleEntity = EntityBase & {
  kind?: "circle";
  construction?: false;
  center: Vector2;
  radius: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "circularArcEntity".
 */
export type CircularArcEntity = EntityBase & {
  kind?: "circularArc";
  construction?: false;
  center: Vector2;
  radius: number;
  startAngleDeg: number;
  endAngleDeg: number;
  clockwise: boolean;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "closedProfileEntity".
 */
export type ClosedProfileEntity = EntityBase & {
  kind?: "closedProfile";
  construction?: false;
  /**
   * @minItems 1
   */
  outerLoop: [Identifier, ...Identifier[]];
  innerLoops: [Identifier, ...Identifier[]][];
  orientation: "clockwise" | "counterclockwise";
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "constructionAxisEntity".
 */
export type ConstructionAxisEntity = EntityBase & {
  kind?: "constructionAxis";
  construction?: true;
  origin: Vector2;
  direction: Vector2;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "nullableTimestamp".
 */
export type NullableTimestamp = string | null;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "jsonValue".
 */
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | {
      [k: string]: JsonValue;
    };
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "feature".
 */
export type Feature =
  | ExtrusionFeature
  | PocketFeature
  | HoleFeature
  | CounterboreFeature
  | CountersinkFeature
  | RevolutionFeature
  | LinearPatternFeature
  | CircularPatternFeature
  | MirrorFeature
  | ChamferFeature
  | FilletFeature
  | ImportedFacetedFeature;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "extrusionFeature".
 */
export type ExtrusionFeature = FeatureBase & {
  operation?: "extrusion";
  booleanMode: "base" | "additive" | "subtractive";
  sketchId: Identifier;
  /**
   * @minItems 1
   */
  profileIds: [Identifier, ...Identifier[]];
  direction: Vector3;
  extent: "blind" | "symmetric" | "throughAll" | "toFace";
  distance?: number | null;
  targetFace?: NullableIdentifier;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "nullableIdentifier".
 */
export type NullableIdentifier = Identifier | null;
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "pocketFeature".
 */
export type PocketFeature = FeatureBase & {
  operation?: "pocket";
  booleanMode: "subtractive";
  sketchId: Identifier;
  /**
   * @minItems 1
   */
  profileIds: [Identifier, ...Identifier[]];
  direction: Vector3;
  extent: "blind" | "throughAll" | "toFace";
  depth: number;
  targetFace?: NullableIdentifier;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "holeFeature".
 */
export type HoleFeature = FeatureBase & {
  operation?: "hole";
  booleanMode: "subtractive";
  holeType: "through" | "blind";
  position: Vector3;
  axis: Vector3;
  diameter: number;
  depth?: number | null;
  terminationFace?: NullableIdentifier;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "counterboreFeature".
 */
export type CounterboreFeature = FeatureBase & {
  operation?: "counterbore";
  booleanMode: "subtractive";
  holeType: "through" | "blind";
  position: Vector3;
  axis: Vector3;
  diameter: number;
  depth?: number | null;
  boreDiameter: number;
  boreDepth: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "countersinkFeature".
 */
export type CountersinkFeature = FeatureBase & {
  operation?: "countersink";
  booleanMode: "subtractive";
  holeType: "through" | "blind";
  position: Vector3;
  axis: Vector3;
  diameter: number;
  depth?: number | null;
  sinkDiameter: number;
  sinkAngleDeg: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "revolutionFeature".
 */
export type RevolutionFeature = FeatureBase & {
  operation?: "revolution";
  booleanMode: "base" | "additive" | "subtractive";
  sketchId: Identifier;
  /**
   * @minItems 1
   */
  profileIds: [Identifier, ...Identifier[]];
  axis: Axis3;
  angleDeg: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "linearPatternFeature".
 */
export type LinearPatternFeature = FeatureBase & {
  operation?: "linearPattern";
  /**
   * @minItems 1
   */
  sourceFeatureIds: [Identifier, ...Identifier[]];
  direction: Vector3;
  count: number;
  spacing: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "circularPatternFeature".
 */
export type CircularPatternFeature = FeatureBase & {
  operation?: "circularPattern";
  /**
   * @minItems 1
   */
  sourceFeatureIds: [Identifier, ...Identifier[]];
  axis: Axis3;
  count: number;
  totalAngleDeg: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "mirrorFeature".
 */
export type MirrorFeature = FeatureBase & {
  operation?: "mirror";
  /**
   * @minItems 1
   */
  sourceFeatureIds: [Identifier, ...Identifier[]];
  plane: Plane3;
  keepOriginals: boolean;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "chamferFeature".
 */
export type ChamferFeature = FeatureBase & {
  operation?: "chamfer";
  /**
   * @minItems 1
   */
  targetEdges: [Identifier, ...Identifier[]];
  width: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "filletFeature".
 */
export type FilletFeature = FeatureBase & {
  operation?: "fillet";
  /**
   * @minItems 1
   */
  targetEdges: [Identifier, ...Identifier[]];
  radius: number;
};
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "importedFacetedFeature".
 */
export type ImportedFacetedFeature = FeatureBase & {
  operation?: "importedFaceted";
  booleanMode: "base" | "additive" | "subtractive";
  sourceArtifactId: Identifier;
  meshSha256: Sha256;
  intent: "fallback" | "reference";
};

/**
 * Authoritative, editable and versioned Mesh2Param feature graph.
 */
export interface CADGraph {
  schemaVersion: "1.0.0";
  id: Identifier;
  name: string;
  units: Units;
  source?: SourceAsset | null;
  sourceCoordinateFrame: SourceCoordinateFrame;
  projectTolerance: ProjectTolerance;
  sketches: Sketch[];
  features: Feature[];
  semanticTopology: SemanticTopologyReference[];
  sourceEvidence: SourceEvidence[];
  userLocks: UserLock[];
  overrides: UserOverride[];
  reconstructionSettings: ReconstructionSettings;
  engineVersions: EngineVersions;
  deterministicSeed: number;
  fitMetrics: FitMetrics;
  validation: ValidationStatus;
  versionMetadata: VersionMetadata;
  /**
   * Namespaced extension data. Core behavior must never depend on an unknown extension.
   */
  extensions?: {
    [k: string]: JsonValue;
  } | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sourceAsset".
 */
export interface SourceAsset {
  format: "stl" | "obj" | "ply" | "cadgraph" | "generated";
  sha256: Sha256;
  originalFileName: string;
  byteSize: number;
  triangleCount?: number | null;
  declaredUnits?: Units | null;
  scaleFactor?: number | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sourceCoordinateFrame".
 */
export interface SourceCoordinateFrame {
  origin: Vector3;
  xAxis: Vector3;
  yAxis: Vector3;
  zAxis: Vector3;
  locked: boolean;
  confidence: Confidence;
  evidenceIds: Identifier[];
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "vector3".
 */
export interface Vector3 {
  x: number;
  y: number;
  z: number;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "projectTolerance".
 */
export interface ProjectTolerance {
  surfaceDeviation: number;
  angularDeviationDeg: number;
  linearResolution: number;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sketch".
 */
export interface Sketch {
  id: Identifier;
  name: string;
  plane: Plane3;
  entities: SketchEntity[];
  constraints: SketchConstraint[];
  profiles: SketchProfile[];
  sourceEvidence: Identifier[];
  confidence: Confidence;
  userLocks: UserLock[];
  overrides: UserOverride[];
  suppressed: boolean;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "plane3".
 */
export interface Plane3 {
  origin: Vector3;
  normal: Vector3;
  xAxis: Vector3;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "entityBase".
 */
export interface EntityBase {
  id: Identifier;
  name?: string | null;
  kind: string;
  construction: boolean;
  sourceEvidence: Identifier[];
  confidence: Confidence;
  locked: boolean;
  suppressed: boolean;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "vector2".
 */
export interface Vector2 {
  x: number;
  y: number;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sketchConstraint".
 */
export interface SketchConstraint {
  id: Identifier;
  kind:
    | "horizontal"
    | "vertical"
    | "coincident"
    | "parallel"
    | "perpendicular"
    | "equalLength"
    | "equalRadius"
    | "concentric"
    | "tangent"
    | "symmetric"
    | "fixed"
    | "distance"
    | "horizontalDistance"
    | "verticalDistance"
    | "angle"
    | "radius"
    | "diameter";
  /**
   * @minItems 1
   */
  entityIds: [Identifier, ...Identifier[]];
  value?: number | null;
  measuredValue?: number | null;
  suggestedNominalValue?: number | null;
  nominalAccepted?: boolean | null;
  unit?: "length" | "angle" | "none" | null;
  driving: boolean;
  sourceEvidence: Identifier[];
  confidence: Confidence;
  locked: boolean;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sketchProfile".
 */
export interface SketchProfile {
  id: Identifier;
  name?: string | null;
  /**
   * @minItems 1
   */
  outerLoop: [Identifier, ...Identifier[]];
  innerLoops: [Identifier, ...Identifier[]][];
  orientation: "clockwise" | "counterclockwise";
  closed: true;
  sourceEvidence: Identifier[];
  confidence: Confidence;
  locked: boolean;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "userLock".
 */
export interface UserLock {
  target: Identifier;
  locked: boolean;
  reason: string;
  lockedAt?: NullableTimestamp;
  lockedBy?: string | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "userOverride".
 */
export interface UserOverride {
  target: Identifier;
  value: JsonValue;
  previousValue?: JsonValue;
  reason: string;
  createdAt?: NullableTimestamp;
  createdBy?: string | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "featureBase".
 */
export interface FeatureBase {
  id: Identifier;
  name: string;
  operation: string;
  order: number;
  dependencies: Identifier[];
  suppressed: boolean;
  sourceEvidence: Identifier[];
  confidence: Confidence;
  userLocks: UserLock[];
  overrides: UserOverride[];
  semanticOutputs: Identifier[];
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "axis3".
 */
export interface Axis3 {
  origin: Vector3;
  direction: Vector3;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "semanticTopologyReference".
 */
export interface SemanticTopologyReference {
  id: Identifier;
  kind: "solid" | "shell" | "face" | "wire" | "edge" | "vertex" | "axis" | "plane";
  producerFeatureId: Identifier;
  role: string;
  generatedFrom: Identifier[];
  status: "resolved" | "unresolved";
  /**
   * Ephemeral diagnostic only; never the semantic identity.
   */
  kernelReference?: string | null;
  lastResolvedAt?: NullableTimestamp;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "sourceEvidence".
 */
export interface SourceEvidence {
  id: Identifier;
  sourceType: "meshPatch" | "meshTriangle" | "sketchEntity" | "feature" | "user" | "engine" | "imported" | "derived";
  sourceIds: Identifier[];
  measuredValue?: number | null;
  suggestedNominalValue?: number | null;
  residual?: number | null;
  confidence: Confidence;
  notes?: string | null;
  metadata?: {
    [k: string]: JsonValue;
  } | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "reconstructionSettings".
 */
export interface ReconstructionSettings {
  maxFeatures: number;
  beamWidth: number;
  candidatesPerResidual: number;
  wallClockSeconds: number;
  maxRebuilds: number;
  minScoreImprovement: number;
  nominalSnappingEnabled: boolean;
  nominalSnapTolerance: number;
  scoreWeights: ScoreWeights;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "scoreWeights".
 */
export interface ScoreWeights {
  rmsDistance: number;
  p95Distance: number;
  maxDistance: number;
  normalAgreement: number;
  volumeDifference: number;
  overlap: number;
  sharpEdgeAlignment: number;
  boundaryAlignment: number;
  unmatchedSource: number;
  excessResult: number;
  complexity: number;
  unsupportedOperation: number;
  evidenceConfidence: number;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "engineVersions".
 */
export interface EngineVersions {
  mesh2param: string;
  contracts: string;
  cadBackend: "OCCT";
  cadQuery: string;
  ocp: string;
  dependencies: {
    [k: string]: string | undefined;
  };
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "fitMetrics".
 */
export interface FitMetrics {
  rmsSurfaceDistance: number;
  p95SurfaceDistance: number;
  maxSurfaceDistance: number;
  normalAgreement: number;
  volumeDifference: number;
  overlap: number;
  unmatchedSourceArea: number;
  excessResultArea: number;
  score: number;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "validationStatus".
 */
export interface ValidationStatus {
  status: "notRun" | "pending" | "valid" | "invalid" | "partial";
  brepValid: boolean | null;
  stepReimportValid: boolean | null;
  toleranceSatisfied: boolean | null;
  checkedAt?: NullableTimestamp;
  lastValidFeatureId?: NullableIdentifier;
  issues: ValidationIssue[];
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "validationIssue".
 */
export interface ValidationIssue {
  code: string;
  message: string;
  severity: "info" | "warning" | "error";
  featureId?: NullableIdentifier;
  semanticReference?: NullableIdentifier;
  details?: {
    [k: string]: JsonValue;
  } | null;
}
/**
 * This interface was referenced by `CADGraph`'s JSON-Schema
 * via the `definition` "versionMetadata".
 */
export interface VersionMetadata {
  versionId: Identifier;
  parentVersionId?: NullableIdentifier;
  createdAt: string;
  createdBy: string;
  message: string;
}
